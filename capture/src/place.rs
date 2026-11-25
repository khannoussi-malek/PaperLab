//! Where the floating paper and its overlay go, across every display. Rects are (x, y, width, height) in global points:
//! the main display's top-left is (0, 0), others sit around it, as macOS lays them out.
//!
//! The page stays whole on the display its centre is on, so a drag carries it onto another monitor and right up to a
//! screen's edge. The overlay is only as big as what it draws (the page and its glow, plus the bubbles while they're
//! out) and always on that display, so nothing depends on a window hanging off a screen's edge.

pub type Rect = [f32; 4];

/// Where the page starts: its centre this far from the main display's bottom-right corner, clear of the Dock.
const START: (f32, f32) = (91.0, 147.0);
/// When no display is known (headless): a laptop screen.
const FALLBACK: Rect = [0.0, 0.0, 1440.0, 900.0];
/// The panel's gap from the page, its width (as the view draws it), the most it grows to, and its margin from a
/// display's edges.
const GAP: f32 = 14.0;
const PANEL_WIDTH: f32 = crate::view::WIDTH;
const PANEL_MAX_HEIGHT: f32 = 620.0;
const MARGIN: f32 = 8.0;

/// The display `point` is on, or the nearest one when it's on none (a monitor just unplugged, a gap between two).
pub fn display_of(point: (f32, f32), displays: &[Rect]) -> Rect {
    let distance = |r: &Rect| {
        let dx = (r[0] - point.0).max(point.0 - (r[0] + r[2])).max(0.0);
        let dy = (r[1] - point.1).max(point.1 - (r[1] + r[3])).max(0.0);
        dx.hypot(dy)
    };
    displays.iter().copied().min_by(|a, b| distance(a).total_cmp(&distance(b))).unwrap_or(FALLBACK)
}

/// The main display: the one at the origin (macOS puts the menu bar's display there), else the first.
pub fn main_display(displays: &[Rect]) -> Rect {
    let at_origin = displays.iter().find(|r| r[0] == 0.0 && r[1] == 0.0);
    at_origin.or(displays.first()).copied().unwrap_or(FALLBACK)
}

/// Where the page starts: bottom right of the main display.
pub fn start(displays: &[Rect]) -> (f32, f32) {
    let [x, y, w, h] = main_display(displays);
    (x + w - START.0, y + h - START.1)
}

/// `centre`, moved just enough that a page `half` its size each way stays whole on the display it's on.
pub fn keep_page(centre: (f32, f32), half: (f32, f32), displays: &[Rect]) -> (f32, f32) {
    let [x, y, w, h] = display_of(centre, displays);
    let clamp = |v: f32, lo: f32, hi: f32| v.clamp(lo, hi.max(lo));
    (clamp(centre.0, x + half.0, x + w - half.0), clamp(centre.1, y + half.1, y + h - half.1))
}

/// The overlay for what it draws (`around`, rects that may poke past the display): their bounding box, cut to the
/// display.
pub fn frame(around: &[Rect], display: Rect) -> Rect {
    let left = around.iter().map(|r| r[0]).fold(f32::INFINITY, f32::min).max(display[0]);
    let top = around.iter().map(|r| r[1]).fold(f32::INFINITY, f32::min).max(display[1]);
    let right = around.iter().map(|r| r[0] + r[2]).fold(f32::NEG_INFINITY, f32::max).min(display[0] + display[2]);
    let bottom = around.iter().map(|r| r[1] + r[3]).fold(f32::NEG_INFINITY, f32::max).min(display[1] + display[3]);
    [left, top, (right - left).max(1.0), (bottom - top).max(1.0)]
}

/// Where the panel opens for a page at `page` on `display`: left of it when there's room, else right; its top level
/// with the page's; kept on that display with room for the panel at its tallest.
pub fn panel_spot(page: Rect, display: Rect) -> (f32, f32) {
    let [px, py, pw, _] = page;
    let [dx, dy, dw, dh] = display;
    let left = px - GAP - PANEL_WIDTH;
    let x = if left >= dx + MARGIN { left } else { px + pw + GAP };
    let x = x.clamp(dx + MARGIN, (dx + dw - PANEL_WIDTH - MARGIN).max(dx + MARGIN));
    let y = (py - 8.0).clamp(dy + MARGIN, (dy + dh - PANEL_MAX_HEIGHT - MARGIN).max(dy + MARGIN));
    (x, y)
}

/// The least the panel is tall while it waits for a drop (its field, mode bar and one line).
const DROP_HEIGHT: f32 = 120.0;

/// Where the panel opens for a drop: under the pointer (`at`), its field's row on it (or, at a display's bottom, the
/// rows below), so letting go lands on the panel; kept on the pointer's display.
pub fn drop_spot(at: (f32, f32), display: Rect) -> (f32, f32) {
    let [dx, dy, dw, dh] = display;
    // up to the display's very edges: the page can sit there, and the pointer on it
    let x = (at.0 - 60.0).clamp(dx, (dx + dw - PANEL_WIDTH).max(dx));
    let y = (at.1 - 28.0).clamp(dy, (dy + dh - DROP_HEIGHT).max(dy));
    (x, y)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A laptop, and a bigger monitor to its right with its top a little higher.
    const LAPTOP: Rect = [0.0, 0.0, 1440.0, 900.0];
    const MONITOR: Rect = [1440.0, -200.0, 2560.0, 1440.0];
    const BOTH: [Rect; 2] = [MONITOR, LAPTOP];
    const HALF: (f32, f32) = (22.0, 28.0);

    #[test]
    fn a_point_belongs_to_its_display_or_the_nearest_one() {
        assert_eq!(display_of((100.0, 100.0), &BOTH), LAPTOP);
        assert_eq!(display_of((2000.0, -100.0), &BOTH), MONITOR);
        assert_eq!(display_of((500.0, 1500.0), &BOTH), LAPTOP, "below the laptop: the laptop is nearest");
        assert_eq!(display_of((3000.0, 50.0), &[LAPTOP]), LAPTOP, "its monitor unplugged: back to what's left");
        assert_eq!(display_of((1.0, 1.0), &[]), FALLBACK);
    }

    #[test]
    fn a_monitor_on_the_left_has_negative_points_and_works_the_same() {
        let left = [-1920.0, 0.0, 1920.0, 1080.0];
        let all = [LAPTOP, left];
        assert_eq!(display_of((-600.0, 500.0), &all), left);
        assert_eq!(keep_page((-5000.0, 500.0), HALF, &all), (-1920.0 + HALF.0, 500.0), "its left edge");
        assert_eq!(main_display(&all), LAPTOP);
        let (x, _) = panel_spot([-1900.0, 300.0, 44.0, 56.0], left);
        assert_eq!(x, -1900.0 + 44.0 + GAP, "no room on its left: right of it, still on that monitor");
    }

    #[test]
    fn it_starts_bottom_right_of_the_main_display_whatever_the_order() {
        assert_eq!(start(&BOTH), (1440.0 - START.0, 900.0 - START.1));
    }

    #[test]
    fn a_page_crosses_onto_another_display_and_reaches_every_edge() {
        assert_eq!(keep_page((1500.0, 300.0), HALF, &BOTH), (1500.0, 300.0), "on the monitor: left alone");
        let corner = (4000.0 - HALF.0, -200.0 + HALF.1);
        assert_eq!(keep_page((9000.0, -999.0), HALF, &BOTH), corner, "the monitor's top-right corner");
        assert_eq!(keep_page((-50.0, 2000.0), HALF, &BOTH), (HALF.0, 900.0 - HALF.1), "the laptop's bottom-left");
    }

    #[test]
    fn the_overlay_holds_what_it_draws_and_never_leaves_the_display() {
        let halo = [1440.0 - 70.0, 400.0, 140.0, 140.0];
        assert_eq!(frame(&[halo], LAPTOP), [1370.0, 400.0, 70.0, 140.0], "cut at the edge");
        let bubbles = [[1100.0, 300.0, 132.0, 34.0], [1150.0, 600.0, 132.0, 34.0]];
        let [x, y, w, h] = frame(&[halo, bubbles[0], bubbles[1]], LAPTOP);
        assert_eq!((x, y, x + w, y + h), (1100.0, 300.0, 1440.0, 634.0));
    }

    #[test]
    fn the_drop_panel_opens_under_the_pointer_even_at_a_screen_edge() {
        for at in [(700.0, 400.0), (1435.0, 880.0), (5.0, 400.0), (3990.0, 1200.0)] {
            let display = display_of(at, &BOTH);
            let (x, y) = drop_spot(at, display);
            let on = at.0 >= x && at.0 < x + PANEL_WIDTH && at.1 >= y && at.1 < y + DROP_HEIGHT;
            assert!(on, "{at:?} not on the panel at {x},{y}");
            assert!(x >= display[0] && x + PANEL_WIDTH <= display[0] + display[2], "{at:?}: off its display");
        }
    }

    #[test]
    fn the_panel_opens_beside_the_page_on_its_own_display() {
        let on_monitor = [1500.0, 100.0, 44.0, 56.0];
        let (x, y) = panel_spot(on_monitor, MONITOR);
        assert_eq!((x, y), (1500.0 + 44.0 + GAP, 92.0), "no room on its left: right of it, on the monitor");
        let right_edge = [4000.0 - 44.0, 1100.0, 44.0, 56.0];
        let (x, y) = panel_spot(right_edge, MONITOR);
        assert_eq!(x, 4000.0 - 44.0 - GAP - PANEL_WIDTH);
        assert_eq!(y, -200.0 + 1440.0 - PANEL_MAX_HEIGHT - MARGIN, "room to grow below");
    }
}
