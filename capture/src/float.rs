//! The floating paper (M79, `--float`): a small page over every app, PaperLab within one click. It bobs gently while
//! idle and can be dragged anywhere. A click opens the Quick Capture panel beside it; while the panel is open the page
//! holds still, a little bigger, so the eye can rest on it. Closing the panel any way lets it float again.

use rune::{
    AppHandle, Color, Cx, DisplayTarget, Drag, El, KeyPolicy, OverlayHandle, OverlayInput, OverlayOptions,
    OverlayPlacement, OverlaySpec, Phase, Tx, el,
};

/// The overlay: the page and its halo, nothing more (the panel is its own window).
const SIZE: (f32, f32) = (150.0, 150.0);
/// The page while idle, and while its panel is open.
const SMALL: (f32, f32) = (36.0, 46.0);
const BIG: (f32, f32) = (44.0, 56.0);
/// A press that travels less than this is a click, not a drag (points).
const CLICK_SLOP: f32 = 4.0;
const GROW_SECONDS: f64 = 0.2;
/// The panel's gap from the page, its width (as the view draws it) and the most it grows to, in points.
const GAP: f32 = 14.0;
const PANEL_WIDTH: f32 = crate::view::WIDTH;
const PANEL_MAX_HEIGHT: f32 = 620.0;
const MARGIN: f32 = 8.0;
/// A click this soon after the panel closed is the one that closed it (focus left the panel for the page): it must
/// not reopen it.
const REOPEN_GRACE: f64 = 0.35;

pub struct Float {
    me: AppHandle<crate::App>,
    /// Its own overlay, to move it while dragged; set once created.
    pub handle: Option<OverlayHandle<Float>>,
    screen: (f32, f32),
    /// The overlay's top-left on the main display, in points.
    origin: (f32, f32),
    /// The origin at the press, while a drag is under way.
    grab: (f32, f32),
    dragging: bool,
    /// Frame clock, seconds.
    t: f64,
    /// Its panel is open.
    open: bool,
    /// A PDF is being dragged over it: it lights up as if open.
    drop_over: bool,
    /// What waits in the Inbox, shown on the page's corner.
    pub badge: usize,
    /// When it last opened or closed, for the grow and shrink.
    since: f64,
    closed_at: f64,
}

impl Float {
    pub fn new(me: AppHandle<crate::App>, screen: (f32, f32)) -> Self {
        let origin = start(screen);
        Float {
            me, handle: None, screen, origin, grab: origin, dragging: false, t: 0.0, open: false, drop_over: false, badge: 0, since: -1.0,
            closed_at: f64::NEG_INFINITY,
        }
    }

    pub fn origin(&self) -> (f32, f32) {
        self.origin
    }

    /// 0 (small, floating) to 1 (big, still), easing over GROW_SECONDS.
    fn openness(&self) -> f32 {
        let k = ease(((self.t - self.since) / GROW_SECONDS).clamp(0.0, 1.0)) as f32;
        if self.open { k } else { 1.0 - k }
    }

    fn set_open(&mut self, open: bool) {
        if open == self.open {
            return;
        }
        let k = f64::from(self.openness()); // from where a half-finished change is, so it reverses smoothly
        self.open = open;
        self.since = self.t - GROW_SECONDS * if open { k } else { 1.0 - k };
    }

    /// The panel closed (Esc, a click outside, a paper opened): float again.
    pub fn panel_closed(&mut self) {
        if self.open {
            self.closed_at = self.t;
        }
        self.set_open(false);
    }

    fn click(&mut self) {
        if self.open {
            self.set_open(false);
            self.me.update(|s, _| s.close());
        } else if self.t - self.closed_at >= REOPEN_GRACE {
            self.set_open(true);
            let page = paper_on_screen(self.origin, BIG);
            crate::show_at(&self.me, panel_spot(page, self.screen));
        }
    }

    /// Files dropped on it: the panel opens beside it (if it isn't open) and takes them, PDFs or not.
    fn dropped(&mut self, event: crate::panel::Event) {
        self.drop_over = false;
        if !self.open {
            self.set_open(true);
            crate::show_at(&self.me, panel_spot(paper_on_screen(self.origin, BIG), self.screen));
        }
        self.me.update(move |s, _| s.dispatch(event));
    }

    /// Press, move, release on the page: a press that barely moves is a click; otherwise the overlay follows the
    /// pointer (Rune reports pointer travel even while the window moves under it).
    fn drag(&mut self, d: &Drag) {
        match d.phase {
            Phase::Down => (self.grab, self.dragging) = (self.origin, false),
            Phase::Move => {
                if self.dragging || d.dx.hypot(d.dy) >= CLICK_SLOP {
                    self.dragging = true;
                    self.origin = on_screen((self.grab.0 + d.dx, self.grab.1 + d.dy), self.screen);
                    if let Some(handle) = &self.handle {
                        handle.set_placement(Some(place(self.origin)));
                    }
                }
            }
            Phase::Up => {
                if !self.dragging && !d.cancelled() {
                    self.click();
                }
                self.dragging = false;
            }
        }
    }
}

fn place(origin: (f32, f32)) -> OverlayPlacement {
    OverlayPlacement::Rect { x: origin.0, y: origin.1, width: SIZE.0, height: SIZE.1 }
}

/// Where it starts: bottom right of a screen this size (points), clear of the Dock's usual height.
pub fn start(screen: (f32, f32)) -> (f32, f32) {
    (screen.0 - SIZE.0 - 16.0, screen.1 - SIZE.1 - 72.0)
}

/// `origin`, moved just enough that the page (at its biggest) stays on a screen this size; the clear halo may leave it.
fn on_screen(origin: (f32, f32), screen: (f32, f32)) -> (f32, f32) {
    let inset = ((SIZE.0 - BIG.0) / 2.0, (SIZE.1 - BIG.1) / 2.0);
    let x = origin.0.clamp(-inset.0, (screen.0 - SIZE.0 + inset.0).max(-inset.0));
    let y = origin.1.clamp(-inset.1, (screen.1 - SIZE.1 + inset.1).max(-inset.1));
    (x, y)
}

/// The page's rect on screen (x, y, width, height) at `size`, for an overlay at `origin`: centred in the overlay.
fn paper_on_screen(origin: (f32, f32), size: (f32, f32)) -> [f32; 4] {
    [origin.0 + (SIZE.0 - size.0) / 2.0, origin.1 + (SIZE.1 - size.1) / 2.0, size.0, size.1]
}

/// Where the panel opens for a page at `page` (x, y, w, h): left of it when there's room, else right; its top level
/// with the page's, both kept on screen with room for the panel at its tallest.
pub fn panel_spot(page: [f32; 4], screen: (f32, f32)) -> (f32, f32) {
    let [px, py, pw, _] = page;
    let left = px - GAP - PANEL_WIDTH;
    let x = if left >= MARGIN { left } else { px + pw + GAP };
    let x = x.clamp(MARGIN, (screen.0 - PANEL_WIDTH - MARGIN).max(MARGIN));
    let y = (py - 8.0).clamp(MARGIN, (screen.1 - PANEL_MAX_HEIGHT - MARGIN).max(MARGIN));
    (x, y)
}

pub fn spec(origin: (f32, f32)) -> rune::ConfiguredOverlay<Float> {
    let options = OverlayOptions {
        display: DisplayTarget::Primary,
        placement: Some(place(origin)),
        // Only the page takes clicks; the clear rest passes them to the app below.
        input: OverlayInput::Regions,
        keys: KeyPolicy::None,
        prewarm: true,
        ..Default::default()
    };
    OverlaySpec::new("PaperLab floating paper", SIZE, view).options(options).poll(poll)
}

fn poll(s: &mut Float, now: f64, _: &mut Tx) -> bool {
    s.t = now;
    true // ponytail: a frame each refresh for the bob (a 150 pt window); measured, and Reduce Motion stops it
}

fn view(s: &Float, cx: &mut Cx<Float>) -> El {
    let dark = cx.system_dark();
    let still = cx.is_reduced_motion();
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let open = if s.drop_over { 1.0 } else { s.openness() };
    let size = (SMALL.0 + (BIG.0 - SMALL.0) * open, SMALL.1 + (BIG.1 - SMALL.1) * open);
    // Floats while idle; held still while dragged or open (the user is looking at it).
    let bob = if still || s.dragging { 0.0 } else { (s.t / 3.2 * std::f64::consts::TAU).sin() as f32 * (1.0 - open) };
    let [px, py, pw, ph] = paper_on_screen((0.0, 0.0), size);
    let (px, py) = (px, py + 3.0 * bob);
    let (cx_, cy_) = (px + pw / 2.0, py + ph / 2.0);
    let halo = 46.0 + 18.0 * open;
    let glow = if dark { 0.32 + 0.16 * open } else { 0.2 + 0.12 * open };
    el().key("float").w_full().h_full()
        .on_drop_files(|s: &mut Float, files, _: &mut Tx| {
            s.dropped(crate::panel::Event::Dropped(files.to_vec()));
        })
        .accepts_extensions(&["pdf"])
        .on_drop_hover(|s: &mut Float, over, _: &mut Tx| s.drop_over = over)
        .on_drop_rejected(|s: &mut Float, _, _: &mut Tx| s.dropped(crate::panel::Event::DropRefused))
        .child(el().key("halo").absolute(cx_ - halo, cy_ - halo).size(halo * 2.0, halo * 2.0)
            .radial_gradient([halo, halo], halo, [(0.0, blue.alpha(glow)), (1.0, blue.alpha(0.0))]))
        .child(paper((px, py), (pw, ph), bob, dark))
        .child(badge(s.badge, (px + pw, py), blue))
}

/// The page, drawn at any size between SMALL and BIG: its lines scale with it.
fn paper(at: (f32, f32), size: (f32, f32), bob: f32, dark: bool) -> El {
    let (w, h) = size;
    let u = w / BIG.0; // 1 at full size
    let ink = Color::BLACK.alpha(0.28);
    let yellow = rune::color::hex("#facc15").expect("a valid colour");
    let slate = rune::color::hex("#475569").expect("a valid colour");
    let line = |top: f32, width: f32, color: Color| {
        el().absolute(8.0 * u, top * u).size(width * u, 3.0 * u).radius(1.5 * u).fill(color)
    };
    el().key("paper").absolute(at.0, at.1).size(w, h).radius(5.0 * u).fill(Color::WHITE.alpha(0.97))
        .border(1.0, if dark { Color::TRANSPARENT } else { slate.alpha(0.25) })
        .shadow(3.0 + 2.0 * u, 8.0 + 6.0 * u, Color::BLACK.alpha(if dark { 0.45 } else { 0.22 }))
        .rotate(0.05 * bob)
        .child(line(11.0, 28.0, ink))
        .child(line(19.0, 28.0, yellow))
        .child(line(27.0, 28.0, ink))
        .child(line(35.0, 18.0, ink))
        .hit()
        .on_drag(|s: &mut Float, d: &mut Drag, _: &mut Tx| s.drag(d))
}

/// The Inbox count on the page's top-right corner (centred on `corner`); nothing when there's nothing new.
fn badge(count: usize, corner: (f32, f32), blue: Color) -> El {
    const D: f32 = 18.0;
    if count == 0 {
        return el();
    }
    let label = if count > 9 { "9+".to_owned() } else { count.to_string() };
    el().key("badge").absolute(corner.0 - D / 2.0, corner.1 - D / 2.0).size(D, D).radius(D / 2.0).fill(blue)
        .border(1.5, Color::WHITE).center().child(rune::text(label).font(rune::TextStyle::new(10.5, 700.0)).color(Color::WHITE))
}

fn ease(x: f64) -> f64 {
    x * x * (3.0 - 2.0 * x)
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCREEN: (f32, f32) = (1440.0, 900.0);

    #[test]
    fn the_panel_opens_left_of_a_paper_with_room_and_right_of_one_without() {
        let right_side = [1300.0, 600.0, 44.0, 56.0];
        let (x, _) = panel_spot(right_side, SCREEN);
        assert_eq!(x, 1300.0 - GAP - PANEL_WIDTH);
        let left_side = [40.0, 200.0, 44.0, 56.0];
        let (x, y) = panel_spot(left_side, SCREEN);
        assert_eq!((x, y), (40.0 + 44.0 + GAP, 192.0));
    }

    #[test]
    fn the_panel_stays_on_screen_with_room_to_grow() {
        let low = [1300.0, 880.0, 44.0, 56.0];
        let (_, y) = panel_spot(low, SCREEN);
        assert_eq!(y, SCREEN.1 - PANEL_MAX_HEIGHT - MARGIN);
        let tiny = panel_spot([10.0, 10.0, 44.0, 56.0], (500.0, 300.0));
        assert!(tiny.0 >= MARGIN && tiny.1 >= MARGIN);
    }

    #[test]
    fn a_drag_keeps_the_page_itself_on_screen() {
        let [x, y, _, h] = paper_on_screen(on_screen((-500.0, 5000.0), SCREEN), BIG);
        assert_eq!((x, y + h), (0.0, SCREEN.1));
        let [x, y, w, _] = paper_on_screen(on_screen((5000.0, -500.0), SCREEN), BIG);
        assert_eq!((x + w, y), (SCREEN.0, 0.0));
        assert_eq!(on_screen((300.0, 200.0), SCREEN), (300.0, 200.0), "inside: left alone");
    }

    #[test]
    fn it_starts_bottom_right_and_its_page_is_centred() {
        let origin = start(SCREEN);
        let [x, y, w, h] = paper_on_screen(origin, BIG);
        assert!(x + w < SCREEN.0 && y + h < SCREEN.1);
        assert_eq!((x - origin.0) * 2.0 + w, SIZE.0);
    }
}
