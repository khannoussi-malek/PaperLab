//! The floating paper (M79, `--float`): a small page over every app, PaperLab within one click. It bobs gently while
//! idle and can be dragged anywhere. A click fans PaperLab's functions out around it as bubbles (bubbles.rs); picking
//! one opens the Quick Capture panel beside it in that mode. While the bubbles or the panel are up the page holds
//! still, a little bigger, so the eye can rest on it. Closing the panel any way lets it float again.
//!
//! `Float` decides (`click`, `pick`, `dropped`, `tick` return what the app should do, as `Act`s); `tell` does it.

use rune::{
    AppHandle, Color, Cx, DisplayTarget, Drag, El, KeyPolicy, OverlayHandle, OverlayInput, OverlayOptions,
    OverlayPlacement, OverlaySpec, Phase, Tx, el,
};

use crate::bubbles::{self, Bubble, PILL, REACH};
use crate::input::Input;
use crate::mode::Mode;
use crate::panel::Event;

/// The overlay: the page, its halo and room for the bubbles around it (the panel is its own window). Only the page
/// and the bubbles take clicks; the clear rest passes them to the app below.
const SIZE: (f32, f32) = (2.0 * REACH.0, 2.0 * REACH.1);
/// Where the page starts: its centre this far from the screen's bottom-right corner, clear of the Dock's usual height.
const START: (f32, f32) = (91.0, 147.0);
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
/// The bubbles fold by themselves after this long without the pointer on one (the overlay never has the keyboard, so
/// there is no Esc, and a click elsewhere goes to another app).
const MENU_IDLE: f64 = 5.0;

/// What the page is doing. Bubbles out or panel open, it is big and still; floating, it bobs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Focus {
    Floating,
    Menu,
    Panel,
}

/// What the floating paper asks of the app.
#[derive(Debug, PartialEq)]
pub enum Act {
    /// Open the panel with its top-left here, in `mode` (None: the last one used), with `query` typed in.
    Show { at: (f32, f32), mode: Option<Mode>, query: Option<String> },
    ClosePanel,
    /// Hand the panel an event (dropped files).
    Take(Event),
}

pub struct Float {
    /// The app, to `tell`; None in tests, which read the `Act`s instead.
    me: Option<AppHandle<crate::App>>,
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
    focus: Focus,
    /// The bubbles, chosen as they come out (the clipboard is read then) and kept until the next time.
    items: Vec<Bubble>,
    /// Reads the clipboard (`clipboard::paste`; a fixed answer in tests).
    paste: fn() -> Option<String>,
    /// When the bubbles last came out or started folding, and how far out each was then, for their animation.
    menu_since: f64,
    menu_from: [f32; bubbles::MAX],
    /// The pointer is on a bubble: they stay out.
    hovered: bool,
    /// When the bubbles came out or the pointer last left one, for MENU_IDLE.
    touched: f64,
    /// A PDF is being dragged over it: it lights up as if open.
    drop_over: bool,
    /// What waits in the Inbox, shown on the page's corner.
    pub badge: usize,
    /// When it last opened or closed, for the grow and shrink.
    since: f64,
    closed_at: f64,
}

impl Float {
    pub fn new(me: Option<AppHandle<crate::App>>, screen: (f32, f32)) -> Self {
        let origin = start(screen);
        Float {
            me, handle: None, screen, origin, grab: origin, dragging: false, t: 0.0, focus: Focus::Floating,
            items: bubbles::menu(None), paste: crate::clipboard::paste, menu_since: f64::NEG_INFINITY,
            menu_from: [0.0; bubbles::MAX], hovered: false, touched: 0.0, drop_over: false, badge: 0,
            since: -1.0,
            closed_at: f64::NEG_INFINITY,
        }
    }

    pub fn origin(&self) -> (f32, f32) {
        self.origin
    }

    /// 0 (small, floating) to 1 (big, still), easing over GROW_SECONDS.
    fn openness(&self) -> f32 {
        let k = ease(((self.t - self.since) / GROW_SECONDS).clamp(0.0, 1.0)) as f32;
        if self.focus == Focus::Floating { 1.0 - k } else { k }
    }

    /// How far out each bubble is now: 0 at the page, 1 in place.
    fn bubbles_out(&self) -> [f32; bubbles::MAX] {
        let (menu, n) = (self.focus == Focus::Menu, self.items.len());
        std::array::from_fn(|i| bubbles::progress(self.t - self.menu_since, i, n, menu, self.menu_from[i]))
    }

    /// A paper the clipboard names by its DOI or arXiv ID (bare or as a doi.org / arxiv.org link). Any other link is
    /// left alone: people copy web pages all day, and a bubble for each would be noise.
    fn copied(&self) -> Option<Input> {
        match crate::input::classify(&(self.paste)()?) {
            input @ (Input::Doi(_) | Input::Arxiv(_)) => Some(input),
            _ => None,
        }
    }

    /// Every change of focus goes through here. The page's grow and the bubbles' pop or fold each start from where a
    /// half-finished one is, so a quick second click reverses smoothly instead of jumping.
    fn focus_on(&mut self, to: Focus) {
        if to == self.focus {
            return;
        }
        if (to == Focus::Menu) != (self.focus == Focus::Menu) {
            self.menu_from = self.bubbles_out();
            (self.menu_since, self.touched, self.hovered) = (self.t, self.t, false);
        }
        let open = to != Focus::Floating;
        if open != (self.focus != Focus::Floating) {
            let k = f64::from(self.openness());
            self.since = self.t - GROW_SECONDS * if open { k } else { 1.0 - k };
        }
        self.focus = to;
    }

    /// The panel closed (Esc, a click outside, a paper opened): float again.
    pub fn panel_closed(&mut self) {
        if self.focus == Focus::Panel {
            self.closed_at = self.t;
        }
        self.focus_on(Focus::Floating);
    }

    /// A click on the page: the bubbles come out, or fold back; with the panel open it closes. A click that comes
    /// just after the panel closed is the one that closed it and does nothing.
    fn click(&mut self) -> Vec<Act> {
        match self.focus {
            Focus::Menu => self.focus_on(Focus::Floating),
            Focus::Panel => {
                self.focus_on(Focus::Floating);
                return vec![Act::ClosePanel];
            }
            Focus::Floating if self.t - self.closed_at >= REOPEN_GRACE => {
                let items = bubbles::menu(self.copied());
                if items != self.items {
                    // other bubbles than a half-finished fold was folding: they all pop from the page
                    (self.items, self.menu_from, self.menu_since) = (items, [0.0; bubbles::MAX], f64::NEG_INFINITY);
                }
                self.focus_on(Focus::Menu);
            }
            Focus::Floating => {}
        }
        vec![]
    }

    /// A bubble picked: they fold and the panel opens beside the page in that mode (Find, looking the clipboard's
    /// paper up, for that bubble); the page stays big and still.
    fn pick(&mut self, bubble: Bubble) -> Vec<Act> {
        self.focus_on(Focus::Panel);
        let (mode, query) = bubble.opens();
        vec![Act::Show { at: self.panel_at(), mode: Some(mode), query }]
    }

    /// Files dropped on it: the panel opens beside it (if it isn't open) and takes them, PDFs or not.
    fn dropped(&mut self, event: Event) -> Vec<Act> {
        self.drop_over = false;
        let show = (self.focus != Focus::Panel).then(|| Act::Show { at: self.panel_at(), mode: None, query: None });
        self.focus_on(Focus::Panel);
        show.into_iter().chain([Act::Take(event)]).collect()
    }

    /// The pointer came onto a bubble or left it.
    fn hover(&mut self, inside: bool) {
        (self.hovered, self.touched) = (inside, self.t);
    }

    /// A frame: the clock moves, and bubbles left alone for MENU_IDLE fold.
    fn tick(&mut self, now: f64) {
        self.t = now;
        if self.focus == Focus::Menu && !self.hovered && self.t - self.touched >= MENU_IDLE {
            self.focus_on(Focus::Floating);
        }
    }

    /// Where the panel opens: beside the page at its biggest.
    fn panel_at(&self) -> (f32, f32) {
        panel_spot(paper_on_screen(self.origin, BIG), self.screen)
    }

    /// Does what the floating paper decided.
    fn tell(&self, acts: Vec<Act>) {
        let Some(me) = &self.me else { return };
        for act in acts {
            match act {
                Act::Show { at, mode, query } => crate::show_at(me, at, mode, query),
                Act::ClosePanel => me.update(|s, _| s.close()),
                Act::Take(event) => me.update(move |s, _| s.dispatch(event)),
            }
        }
    }

    /// Press, move, release on the page: a press that barely moves is a click; otherwise the overlay follows the
    /// pointer (Rune reports pointer travel even while the window moves under it).
    fn drag(&mut self, d: &Drag) -> Vec<Act> {
        match d.phase {
            Phase::Down => (self.grab, self.dragging) = (self.origin, false),
            Phase::Move => {
                if self.dragging || d.dx.hypot(d.dy) >= CLICK_SLOP {
                    (self.dragging, self.touched) = (true, self.t); // moving the page is using the bubbles
                    self.origin = on_screen((self.grab.0 + d.dx, self.grab.1 + d.dy), self.screen);
                    if let Some(handle) = &self.handle {
                        handle.set_placement(Some(place(self.origin)));
                    }
                }
            }
            Phase::Up => {
                let clicked = !self.dragging && !d.cancelled();
                self.dragging = false;
                if clicked {
                    return self.click();
                }
            }
        }
        vec![]
    }
}

fn place(origin: (f32, f32)) -> OverlayPlacement {
    OverlayPlacement::Rect { x: origin.0, y: origin.1, width: SIZE.0, height: SIZE.1 }
}

/// Where it starts on a screen this size (points): its page bottom right (START).
pub fn start(screen: (f32, f32)) -> (f32, f32) {
    (screen.0 - START.0 - SIZE.0 / 2.0, screen.1 - START.1 - SIZE.1 / 2.0)
}

/// `origin`, moved just enough that the page (at its biggest) stays on a screen this size; the clear rest may leave it.
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
    s.tick(now);
    // ponytail: a frame each refresh for the bob and the bubbles (the overlay is ~500 x 400 pt, mostly clear); if it
    // shows in Activity Monitor, shrink the overlay to the page while the bubbles are folded.
    true
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
        .child(el().key("halo").absolute(cx_ - halo, cy_ - halo).size(halo * 2.0, halo * 2.0)
            .radial_gradient([halo, halo], halo, [(0.0, blue.alpha(glow)), (1.0, blue.alpha(0.0))]))
        .children(menu(s, (cx_, cy_), still, dark))
        .child(paper((px, py), (pw, ph), bob, dark))
        .child(badge(s.badge, (px + pw, py), blue))
}

/// The bubbles, flying out from the page's centre (`centre`, in the overlay) to their spots, or back. Only bubbles
/// on their way out or out take clicks; folding ones don't, and folded or not-yet-started ones aren't drawn at all, so
/// nothing invisible catches a click.
fn menu(s: &Float, centre: (f32, f32), still: bool, dark: bool) -> Vec<El> {
    let on_screen = (s.origin.0 + centre.0, s.origin.1 + centre.1);
    let spots = bubbles::spots(on_screen, s.screen, s.items.len());
    let home = (centre.0 - PILL.0 / 2.0, centre.1 - PILL.1 / 2.0);
    let menu = s.focus == Focus::Menu;
    let out = s.bubbles_out();
    s.items.iter().zip(spots).enumerate().filter_map(|(i, (bubble, spot))| {
        let k = if still { f32::from(u8::from(menu)) } else { out[i] };
        let to = (spot.0 - s.origin.0, spot.1 - s.origin.1);
        let at = (home.0 + (to.0 - home.0) * k, home.1 + (to.1 - home.1) * k);
        let pill = bubbles::pill(i, bubble, s.badge, dark, k).absolute(at.0, at.1);
        let bubble = bubble.clone();
        match (menu, k > 0.0) {
            (true, true) => Some(pill.hit()
                .on_press(move |s: &mut Float| {
                    let acts = s.pick(bubble.clone());
                    s.tell(acts);
                })
                .on_hover_change(|s: &mut Float, inside, _: &mut Tx| s.hover(inside))),
            (false, true) => Some(pill),
            (_, false) => None,
        }
    }).collect()
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
        .on_drag(|s: &mut Float, d: &mut Drag, _: &mut Tx| {
            let acts = s.drag(d);
            s.tell(acts);
        })
        // Drops land on the page only, never on the clear overlay around it, which belongs to the app below.
        .on_drop_files(|s: &mut Float, files, _: &mut Tx| {
            let acts = s.dropped(Event::Dropped(files.to_vec()));
            s.tell(acts);
        })
        .accepts_extensions(&["pdf"])
        .on_drop_hover(|s: &mut Float, over, _: &mut Tx| s.drop_over = over)
        .on_drop_rejected(|s: &mut Float, _, _: &mut Tx| {
            let acts = s.dropped(Event::DropRefused);
            s.tell(acts);
        })
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

    /// A floating paper with nothing to tell (its `Act`s are the answer) and an empty clipboard, its clock at `t`.
    fn paper_at(t: f64) -> Float {
        let mut f = Float::new(None, SCREEN);
        f.paste = || None;
        f.tick(t);
        f
    }

    #[test]
    fn a_copied_doi_adds_a_first_bubble_that_looks_it_up_in_find() {
        let mut f = paper_at(10.0);
        f.paste = || Some("  https://doi.org/10.48550/arXiv.1706.03762 \n".into());
        f.click();
        assert_eq!(f.items[0], Bubble::Copied(Input::Doi("10.48550/arXiv.1706.03762".into())));
        assert_eq!(f.items.len(), bubbles::MAX);
        let acts = f.pick(f.items[0].clone());
        let query = Some("10.48550/arXiv.1706.03762".to_owned());
        assert_eq!(acts, vec![Act::Show { at: f.panel_at(), mode: Some(Mode::Find), query }]);
    }

    #[test]
    fn an_arxiv_link_counts_and_a_changed_clipboard_pops_its_bubbles_from_the_page() {
        let mut f = paper_at(10.0);
        f.paste = || Some("https://arxiv.org/abs/1706.03762".into());
        f.click();
        assert_eq!(f.items[0], Bubble::Copied(Input::Arxiv("1706.03762".into())));
        f.tick(11.0);
        f.click(); // the six start folding from where they are
        f.paste = || None;
        f.tick(11.02);
        f.click(); // the modes alone, reopened mid-fold
        assert_eq!(f.items[0], Bubble::Mode(Mode::Find));
        assert_eq!(f.bubbles_out()[0], 0.0, "Find pops from the page, not from where the copied bubble was");
    }

    #[test]
    fn copied_prose_a_web_page_or_nothing_adds_no_bubble() {
        for paste in [(|| None) as fn() -> Option<String>, || Some("a sentence about attention".into()),
            || Some("https://news.example.com/today".into())] {
            let mut f = paper_at(10.0);
            f.paste = paste;
            f.click();
            assert_eq!(f.items, bubbles::menu(None));
        }
    }

    #[test]
    fn a_click_brings_the_bubbles_out_and_a_second_folds_them() {
        let mut f = paper_at(10.0);
        assert_eq!(f.click(), vec![], "no panel yet: the bubbles are the menu");
        assert_eq!(f.focus, Focus::Menu, "bubbles out, page big and still");
        f.tick(11.0);
        assert_eq!(f.click(), vec![]);
        assert_eq!(f.focus, Focus::Floating, "folded, floating again");
    }

    #[test]
    fn picking_a_bubble_opens_the_panel_beside_the_page_in_that_mode() {
        let mut f = paper_at(10.0);
        f.click();
        let acts = f.pick(Bubble::Mode(Mode::Ask));
        assert_eq!(acts, vec![Act::Show { at: f.panel_at(), mode: Some(Mode::Ask), query: None }]);
        assert_eq!(f.focus, Focus::Panel, "the bubbles fold; the page stays still beside its panel");
        assert_eq!(f.click(), vec![Act::ClosePanel], "a click on the page closes the panel");
    }

    #[test]
    fn the_click_that_closed_the_panel_brings_nothing_out() {
        let mut f = paper_at(10.0);
        f.click();
        f.pick(Bubble::Mode(Mode::Find));
        f.panel_closed(); // focus left the panel for the page
        assert_eq!(f.click(), vec![]);
        assert_eq!(f.focus, Focus::Floating);
        f.tick(10.5);
        f.click();
        assert_eq!(f.focus, Focus::Menu, "a later click does");
    }

    #[test]
    fn the_bubbles_fold_by_themselves_unless_the_pointer_is_on_one() {
        let mut f = paper_at(10.0);
        f.click();
        f.hover(true);
        f.tick(10.0 + 3.0 * MENU_IDLE);
        assert_eq!(f.focus, Focus::Menu, "pointed at: they stay");
        f.hover(false);
        f.tick(10.0 + 4.0 * MENU_IDLE - 0.1);
        assert_eq!(f.focus, Focus::Menu, "not yet");
        f.tick(10.0 + 4.0 * MENU_IDLE);
        assert_eq!(f.focus, Focus::Floating, "left alone: folded, floating again");
    }

    #[test]
    fn a_drop_while_the_bubbles_are_out_opens_the_panel_and_hands_it_the_files() {
        let mut f = paper_at(10.0);
        f.click();
        let acts = f.dropped(Event::DropRefused);
        assert_eq!(acts, vec![Act::Show { at: f.panel_at(), mode: None, query: None }, Act::Take(Event::DropRefused)]);
        assert_eq!(f.focus, Focus::Panel);
        assert_eq!(f.dropped(Event::DropRefused), vec![Act::Take(Event::DropRefused)], "panel open: just the files");
    }

    #[test]
    fn the_bubbles_are_drawn_only_once_out_and_a_press_on_one_picks_it() {
        use rune::{Env, Runtime};
        let mut rt = Runtime::new(paper_at(10.0), view, SIZE, Env { system_dark: false, scale: 2.0 });
        rt.frame(0.0);
        assert!(rt.find("bubble-0").is_none(), "folded: nothing drawn, nothing to catch a click");
        rt.update(|s, _| {
            s.click();
            s.tick(11.0);
        });
        rt.frame(1.0 / 60.0);
        let (x, y) = rt.find("bubble-2").expect("Ask is out");
        rt.pointer_down(x, y);
        rt.pointer_up(x, y);
        rt.frame(1.0 / 60.0);
        assert_eq!(rt.state.focus, Focus::Panel, "picked: folded, the panel would open");
    }

    #[test]
    fn a_quick_second_click_folds_the_bubbles_from_where_they_are() {
        let mut f = paper_at(10.0);
        f.click();
        f.tick(10.08); // the first bubble partly out, the last not started
        let then = f.bubbles_out();
        assert!(then[0] > 0.0 && then[0] < 1.0 && then[4] == 0.0, "{then:?}");
        f.click();
        assert_eq!(f.bubbles_out(), then, "the fold starts where the pop was: nothing jumps");
        f.tick(10.2); // the top bubble folds last
        assert!(f.bubbles_out()[0] < then[0] && f.bubbles_out()[4] == 0.0);
    }

    #[test]
    fn dragging_the_page_keeps_the_bubbles_out() {
        use rune::{Env, Runtime};
        let mut rt = Runtime::new(paper_at(10.0), view, SIZE, Env { system_dark: false, scale: 2.0 });
        rt.update(|s, _| { s.click(); });
        rt.frame(0.0);
        let (x, y) = rt.find("paper").expect("the page");
        rt.pointer_down(x, y);
        rt.update(|s, _| s.tick(10.0 + MENU_IDLE - 0.5));
        rt.pointer_move(x + 40.0, y);
        rt.frame(1.0 / 60.0);
        rt.update(|s, _| s.tick(10.0 + MENU_IDLE + 1.0));
        assert!(rt.state.dragging, "the drag is under way");
        assert_eq!(rt.state.focus, Focus::Menu, "being moved isn't being left alone");
    }

    #[test]
    fn it_starts_bottom_right_and_its_page_is_centred() {
        let origin = start(SCREEN);
        let [x, y, w, h] = paper_on_screen(origin, BIG);
        assert!(x + w < SCREEN.0 && y + h < SCREEN.1);
        assert_eq!((x - origin.0) * 2.0 + w, SIZE.0);
    }
}
