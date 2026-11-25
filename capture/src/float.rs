//! The floating paper (M79, `--float`): a small page over every app, PaperLab within one click. It bobs gently while
//! idle and can be dragged anywhere, onto any display and right up to its edges (place.rs). A click fans PaperLab's
//! functions out around it as bubbles (bubbles.rs); picking one opens the Quick Capture panel beside it in that mode.
//! While the bubbles or the panel are up the page holds still, a little bigger, so the eye can rest on it. Closing the
//! panel any way lets it float again. Left against a screen's side it tucks into it (tuck.rs), a tab and a grip
//! showing, and slides back out when pointed at, needed, or brought a file.
//!
//! `Float` decides (`click`, `pick`, `dropped`, `tick` return what the app should do, as `Act`s); `tell` does it.

use rune::{
    AppHandle, Color, Cx, DisplayTarget, Drag, El, KeyPolicy, OverlayHandle, OverlayInput, OverlayOptions,
    OverlayPlacement, OverlaySpec, Phase, Tx, el,
};

use crate::bubbles::{self, Bubble, PILL, Pick};
use crate::input::Input;
use crate::mode::Mode;
use crate::panel::Event;
use crate::place::{self, Edge, Rect};
use crate::tuck::{self, Tuck};

/// How far the glow (and the Inbox badge) reaches from the page's centre: the overlay's size while the bubbles are in.
/// Only the page and the bubbles take clicks; the clear rest passes them to the app below.
const HALO: f32 = 70.0;
/// How near the tucked strip the pointer must come to bring the page out.
const PEEK_NEAR: f32 = 8.0;
/// How often it asks macOS for the displays again (a monitor plugged in or out; Rune doesn't say).
const DISPLAYS_EVERY: f64 = 2.0;
/// The page while idle, and while its panel is open.
const SMALL: (f32, f32) = (36.0, 46.0);
const BIG: (f32, f32) = (44.0, 56.0);
/// A press that travels less than this is a click, not a drag (points).
const CLICK_SLOP: f32 = 4.0;
const GROW_SECONDS: f64 = 0.2;
/// A click this soon after the panel closed is the one that closed it (focus left the panel for the page): it must
/// not reopen it.
const REOPEN_GRACE: f64 = 0.35;
/// The bubbles fold by themselves after this long without the pointer on one (the overlay never has the keyboard, so
/// there is no Esc, and a click elsewhere goes to another app).
const MENU_IDLE: f64 = 5.0;
/// "Hide for an hour" (a screen share, a talk); the shortcut brings it back sooner. It fades back in over FADE_IN.
const HIDE_FOR: f64 = 3600.0;
const FADE_IN: f64 = 0.4;
/// The badge's pulse when the Inbox grows.
const PULSE: f32 = 0.35;
const PULSE_SECONDS: f64 = 0.5;
/// How often a hidden paper checks whether its hour is up. The frame clock stops while the Mac sleeps, so the hour is
/// an hour awake; the shortcut brings it back at any time.
const HIDDEN_POLL: std::time::Duration = std::time::Duration::from_secs(1);

/// What the page is doing. Bubbles out or panel open, it is big and still; floating, it bobs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Focus {
    Floating,
    Menu,
    Panel,
}

/// What a drag from another app carries, as far as the paper cares.
#[derive(Clone, Debug, PartialEq)]
enum Carried {
    Files,
    Link(String),
    Nothing,
}

/// What the floating paper asks of the app.
#[derive(Debug, PartialEq)]
pub enum Act {
    /// Open the panel with its top-left here, in `mode` (None: the last one used), with `query` typed in.
    Show { at: (f32, f32), mode: Option<Mode>, query: Option<String> },
    ClosePanel,
    OpenPaperLab,
    /// Hand the panel an event (dropped files).
    Take(Event),
}

pub struct Float {
    /// The app, to `tell`; None in tests, which read the `Act`s instead.
    me: Option<AppHandle<crate::App>>,
    /// Its own overlay, to move it while dragged; set once created.
    pub handle: Option<OverlayHandle<Float>>,
    /// The page's centre, in global points (place.rs).
    page: (f32, f32),
    /// The displays, and how to read them again (`displays::read`; a fixed list in tests), and when it last did.
    displays: Vec<Rect>,
    read_displays: fn() -> Vec<Rect>,
    displays_at: f64,
    /// Where the overlay is: what it draws, cut to the page's display (`frame`).
    placed: Rect,
    /// Tucked into a side of its display, or free.
    tuck: Tuck,
    /// The page's centre at the press, while a drag is under way.
    grab: (f32, f32),
    /// The pointer at the press, as AppKit has it (bottom-left points), until the release.
    pressed_at: Option<(f64, f64)>,
    /// Reads the pointer (`displays::pointer`, AppKit's bottom-left points; a fixed answer in tests).
    read_pointer: fn() -> Option<(f64, f64)>,
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
    /// Senses a drag from another app (file_drag.rs; fixed answers in tests): the drag pasteboard's count when the
    /// button went down (None while it's up), and what this drag carries, read once when it first comes over the
    /// page (None until then); for a link, whether it's over the page now (the page lights up as its target).
    sense: fn() -> crate::file_drag::Sense,
    carries_files: fn() -> bool,
    drag_link: fn() -> Option<String>,
    drag_start: Option<isize>,
    carried: Option<Carried>,
    link_over: bool,
    /// Until when it's hidden (the frame clock); nothing is drawn or takes a click before then.
    hidden_until: f64,
    /// What waits in the Inbox, shown on the page's corner, and when it last grew (the badge pulses once).
    badge: usize,
    badge_grew: f64,
    /// When it last opened or closed, for the grow and shrink.
    since: f64,
    closed_at: f64,
}

impl Float {
    pub fn new(me: Option<AppHandle<crate::App>>, displays: Vec<Rect>) -> Self {
        let page = place::start(&displays);
        let mut float = Float {
            me, handle: None, page, displays, read_displays: crate::displays::read, displays_at: 0.0,
            placed: [0.0; 4], tuck: Tuck::free(), grab: page, pressed_at: None, read_pointer: crate::displays::pointer,
            dragging: false, t: 0.0, focus: Focus::Floating,
            items: bubbles::menu(None), paste: crate::clipboard::paste, menu_since: f64::NEG_INFINITY,
            menu_from: [0.0; bubbles::MAX], hovered: false, touched: 0.0, badge: 0,
            sense: crate::file_drag::sense, carries_files: crate::file_drag::carries_files, drag_start: None,
            drag_link: crate::file_drag::link, carried: None, link_over: false,
            badge_grew: f64::NEG_INFINITY, hidden_until: f64::NEG_INFINITY, since: -1.0,
            closed_at: f64::NEG_INFINITY,
        };
        float.placed = float.frame();
        float
    }

    /// Where the overlay is, for creating it.
    pub fn placed(&self) -> Rect {
        self.placed
    }

    /// The display the page is on.
    fn display(&self) -> Rect {
        place::display_of(self.page, &self.displays)
    }

    /// The page's rect at `size`, centred on its centre.
    fn page_rect(&self, size: (f32, f32)) -> Rect {
        [self.page.0 - size.0 / 2.0, self.page.1 - size.1 / 2.0, size.0, size.1]
    }

    /// The page's centre as drawn: slid toward its edge as far as it's tucked.
    fn drawn(&self) -> (f32, f32) {
        let Some(edge) = self.tuck.edge() else { return self.page };
        let to = place::tucked(self.page, (SMALL.0 / 2.0, SMALL.1 / 2.0), edge, self.display(), tuck::TAB);
        let k = self.tuck.amount(self.t);
        (self.page.0 + (to.0 - self.page.0) * k, self.page.1 + (to.1 - self.page.1) * k)
    }

    /// The page's rect as drawn, at `size`.
    fn drawn_rect(&self, size: (f32, f32)) -> Rect {
        let (x, y) = self.drawn();
        [x - size.0 / 2.0, y - size.1 / 2.0, size.0, size.1]
    }

    /// Tucked: out while pointed at, open, dragged or brought a file; back in a moment after the last of those.
    fn tuck_tick(&mut self) {
        if self.tuck.edge().is_none() {
            return;
        }
        let pointed = self.pointer().is_some_and(|p| near(self.drawn_rect(SMALL), p, PEEK_NEAR));
        let brought = matches!(self.carried, Some(Carried::Files | Carried::Link(_)));
        let wanted_out = pointed || self.focus != Focus::Floating || self.dragging || brought;
        self.tuck.watch(self.t, wanted_out);
    }

    /// A drag ended: against an edge, the page tucks into it (once the pointer has left it); elsewhere it's free.
    fn snap(&mut self) {
        let edge = place::edge_near(self.page_rect(BIG), self.display(), tuck::SNAP);
        self.tuck.snap(edge, self.t);
    }

    /// Each bubble's top-left, in global points: the crescent on the page's display.
    fn spots(&self) -> Vec<(f32, f32)> {
        let [dx, dy, dw, dh] = self.display();
        let local = (self.page.0 - dx, self.page.1 - dy);
        bubbles::spots(local, (dw, dh), self.items.len()).into_iter().map(|(x, y)| (x + dx, y + dy)).collect()
    }

    /// What the overlay must hold: the page's glow, and the bubbles while any is out, cut to its display.
    fn frame(&self) -> Rect {
        let (x, y) = self.drawn();
        let glow = [x - HALO, y - HALO, 2.0 * HALO, 2.0 * HALO];
        let out = self.focus == Focus::Menu || self.bubbles_out().iter().any(|&k| k > 0.0);
        let pills = self.spots().into_iter().filter(|_| out).map(|(x, y)| [x, y, PILL.0, PILL.1]);
        place::frame(&std::iter::once(glow).chain(pills).collect::<Vec<_>>(), self.display())
    }

    /// Moves or resizes the overlay when what it must hold changed.
    fn place_overlay(&mut self) {
        let frame = self.frame();
        if frame != self.placed {
            self.placed = frame;
            if let Some(handle) = &self.handle {
                handle.set_placement(Some(placement(frame)));
            }
        }
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

    /// A paper the clipboard names: its DOI or arXiv ID (bare or as a doi.org / arxiv.org link), or a link to it (a
    /// DOI in it, or a paper site's: see `names_a_paper`). Any other link is left alone: people copy web pages all
    /// day, and a bubble for each would be noise.
    fn copied(&self) -> Option<Input> {
        match crate::input::classify(&(self.paste)()?) {
            input @ (Input::Doi(_) | Input::Arxiv(_)) => Some(input),
            Input::Link(link) if crate::input::names_a_paper(&link) => Some(Input::Link(link)),
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
        let items = || bubbles::menu(self.copied());
        self.press(items())
    }

    /// A right-click (or control-click) on the page: the paper's own bubbles, open PaperLab or hide it.
    fn right_click(&mut self) -> Vec<Act> {
        if self.dragging {
            return vec![]; // mid-drag: the page is being moved, not asked for anything
        }
        self.press(bubbles::paper_menu())
    }

    /// A press on the page: `items` come out, or the bubbles fold back; with the panel open it closes.
    fn press(&mut self, items: Vec<Bubble>) -> Vec<Act> {
        match self.focus {
            Focus::Menu => self.focus_on(Focus::Floating),
            Focus::Panel => {
                self.focus_on(Focus::Floating);
                return vec![Act::ClosePanel];
            }
            Focus::Floating if self.t - self.closed_at >= REOPEN_GRACE => {
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

    /// The Inbox's count, after each refresh: more than before pulses the badge once, so something new is noticed
    /// without anything popping up.
    pub fn set_badge(&mut self, count: usize) {
        if count > self.badge {
            self.badge_grew = self.t;
        }
        self.badge = count;
    }

    /// The badge's size: 1, swelling to 1 + PULSE and back over PULSE_SECONDS after the count grew.
    fn badge_scale(&self) -> f32 {
        let k = (self.t - self.badge_grew) / PULSE_SECONDS;
        if (0.0..1.0).contains(&k) { 1.0 + PULSE * (k * std::f64::consts::PI).sin() as f32 } else { 1.0 }
    }

    fn hidden(&self) -> bool {
        self.t < self.hidden_until
    }

    /// Back now (the shortcut was pressed while it was hidden).
    pub fn unhide(&mut self) {
        if self.hidden() {
            self.hidden_until = self.t;
        }
    }

    /// A bubble picked: they fold and the panel opens beside the page in that mode (Find, looking the clipboard's
    /// paper up, for that bubble); the page stays big and still.
    fn pick(&mut self, bubble: Bubble) -> Vec<Act> {
        match bubble.pick() {
            Pick::Panel(mode, query) => {
                self.focus_on(Focus::Panel);
                vec![Act::Show { at: self.panel_at(), mode: Some(mode), query }]
            }
            Pick::OpenPaperLab => {
                self.focus_on(Focus::Floating);
                vec![Act::OpenPaperLab]
            }
            Pick::Hide => {
                self.focus_on(Focus::Floating);
                self.dragging = false; // its page is gone: no gesture can finish on it
                self.hidden_until = self.t + HIDE_FOR;
                vec![]
            }
        }
    }

    /// A frame's look at the mouse, for a drag from another app (the drag pasteboard changed since the button went
    /// down). What it carries is read once, when it first comes over the page. Files: the panel opens under the
    /// pointer for the drop, once per drag, and the drag's end tells it. A link: the page lights up while it's over
    /// it, and let go there, the panel opens in Find with the link looked up (read from the drag itself, so the
    /// browser needn't accept a drop). Anything else: nothing.
    fn watch_drag(&mut self) -> Vec<Act> {
        let now = (self.sense)();
        match (now.button, self.drag_start) {
            (true, None) => {
                (self.drag_start, self.carried, self.link_over) = (Some(now.count), None, false);
                vec![]
            }
            (false, Some(_)) => {
                self.drag_start = None;
                let over = std::mem::take(&mut self.link_over);
                match self.carried.take() {
                    Some(Carried::Files) => vec![Act::Take(Event::DragEnded)],
                    Some(Carried::Link(link)) if over => {
                        self.focus_on(Focus::Panel);
                        vec![Act::Show { at: self.panel_at(), mode: Some(Mode::Find), query: Some(link) }]
                    }
                    _ => vec![],
                }
            }
            (true, Some(start)) if !self.dragging && now.count != start => {
                let over = self.pointer().filter(|&at| self.over_page(at));
                if let Some(Carried::Link(_)) = self.carried {
                    self.link_over = over.is_some();
                }
                let (None, Some(at)) = (&self.carried, over) else { return vec![] };
                let carried = if (self.carries_files)() {
                    Carried::Files
                } else {
                    (self.drag_link)().map_or(Carried::Nothing, Carried::Link)
                };
                self.carried = Some(carried.clone());
                match carried {
                    Carried::Files => {
                        self.focus_on(Focus::Panel);
                        let at = place::drop_spot(at, place::display_of(at, &self.displays));
                        vec![Act::Show { at, mode: Some(Mode::Find), query: None }, Act::Take(Event::DropOffered)]
                    }
                    Carried::Link(_) => {
                        self.link_over = true;
                        vec![]
                    }
                    Carried::Nothing => vec![],
                }
            }
            _ => vec![],
        }
    }

    /// The pointer in global points, top-left origin (place.rs), when AppKit can say.
    fn pointer(&self) -> Option<(f32, f32)> {
        let main_height = f64::from(place::main_display(&self.displays)[3]);
        (self.read_pointer)().map(|(x, y)| (x as f32, (main_height - y) as f32))
    }

    /// `at` is on the page as drawn (its tab, when tucked), or near enough to it: a drop is aimed less carefully than
    /// a click.
    fn over_page(&self, at: (f32, f32)) -> bool {
        near(self.drawn_rect(BIG), at, 16.0)
    }

    /// The pointer came onto a bubble or left it.
    fn hover(&mut self, inside: bool) {
        (self.hovered, self.touched) = (inside, self.t);
    }

    /// A frame: the clock moves, and bubbles left alone for MENU_IDLE fold.
    fn tick(&mut self, now: f64) {
        self.t = now;
        if self.t - self.displays_at >= DISPLAYS_EVERY {
            self.displays_at = self.t;
            let fresh = (self.read_displays)();
            if !fresh.is_empty() && fresh != self.displays {
                // a monitor came or went: a page left on one that's gone moves to the nearest one there is
                self.displays = fresh;
                self.page = place::keep_page(self.page, (BIG.0 / 2.0, BIG.1 / 2.0), &self.displays);
                self.tuck.release(); // its side may be gone or moved: free until it's let go against one again
            }
        }
        if self.focus == Focus::Menu && !self.hovered && self.t - self.touched >= MENU_IDLE {
            self.focus_on(Focus::Floating);
        }
        self.tuck_tick();
        self.place_overlay(); // the bubbles came out or finished folding: the overlay grows or shrinks to them
    }

    /// Where the panel opens: beside the page at its biggest, on its display.
    fn panel_at(&self) -> (f32, f32) {
        place::panel_spot(self.page_rect(BIG), self.display())
    }

    /// Does what the floating paper decided.
    fn tell(&self, acts: Vec<Act>) {
        let Some(me) = &self.me else { return };
        for act in acts {
            match act {
                Act::Show { at, mode, query } => crate::show_at(me, at, mode, query),
                Act::ClosePanel => me.update(|s, _| s.close()),
                Act::OpenPaperLab => me.update(|s, _| s.perform(crate::panel::Effect::OpenPaperLab)),
                Act::Take(event) => me.update(move |s, _| s.dispatch(event)),
            }
        }
    }

    /// The press ends: a click if it barely moved; a drag ends against an edge or not (`snap`).
    fn release(&mut self, cancelled: bool) -> Vec<Act> {
        let (dragged, clicked) = (self.dragging, !self.dragging && !cancelled);
        (self.dragging, self.pressed_at) = (false, None);
        if dragged {
            self.snap();
        }
        if clicked { self.click() } else { vec![] }
    }

    fn grab_page(&mut self) {
        // from where it's drawn: a tucked page is grabbed by its tab, not where it would be out
        (self.grab, self.pressed_at, self.dragging) = (self.drawn(), (self.read_pointer)(), false);
    }

    /// How far the pointer has gone since the press. From AppKit when it can say: Rune measures it from the window's
    /// moves in its current scale, which jumps when the page crosses onto a display of another scale (a 1x monitor
    /// beside a 2x laptop) and threw it back. Rune's own `rune` travel otherwise.
    fn travel(&self, rune: (f32, f32)) -> (f32, f32) {
        match (self.pressed_at, (self.read_pointer)()) {
            // AppKit's y grows upward, ours downward: only the difference's sign flips, no screen height involved
            (Some(from), Some(to)) => ((to.0 - from.0) as f32, (from.1 - to.1) as f32),
            _ => rune,
        }
    }

    /// The pointer `travel` points from the press: past CLICK_SLOP the page follows it, whole on whichever display
    /// it's over, and the overlay with it.
    fn drag_to(&mut self, travel: (f32, f32)) {
        if self.dragging || travel.0.hypot(travel.1) >= CLICK_SLOP {
            (self.dragging, self.touched) = (true, self.t); // moving the page is using the bubbles
            self.tuck.release(); // taken off its side; a release there tucks it again
            let to = (self.grab.0 + travel.0, self.grab.1 + travel.1);
            self.page = place::keep_page(to, (BIG.0 / 2.0, BIG.1 / 2.0), &self.displays);
            self.place_overlay();
        }
    }

    /// Press, move, release on the page: a press that barely moves is a click; otherwise the overlay follows the
    /// pointer (Rune reports pointer travel even while the window moves under it).
    fn drag(&mut self, d: &Drag) -> Vec<Act> {
        match d.phase {
            Phase::Down => self.grab_page(),
            Phase::Move => {
                let travel = self.travel((d.dx, d.dy));
                self.drag_to(travel);
            }
            Phase::Up => return self.release(d.cancelled()),
        }
        vec![]
    }
}

fn placement(frame: Rect) -> OverlayPlacement {
    let [x, y, width, height] = frame;
    OverlayPlacement::Rect { x, y, width, height } // global points on the primary target: any display (rune docs)
}

pub fn spec(frame: Rect) -> rune::ConfiguredOverlay<Float> {
    let options = OverlayOptions {
        display: DisplayTarget::Primary,
        placement: Some(placement(frame)),
        // Only the page takes clicks; the clear rest passes them to the app below.
        input: OverlayInput::Regions,
        keys: KeyPolicy::None,
        prewarm: true,
        ..Default::default()
    };
    OverlaySpec::new("PaperLab floating paper", (frame[2], frame[3]), view).options(options).poll(poll)
}

fn poll(s: &mut Float, now: f64, tx: &mut Tx) -> bool {
    s.tick(now);
    if s.hidden() {
        // Nothing to draw: one look a second keeps the clock (and the hour) going instead of a frame each refresh.
        tx.wake_after(HIDDEN_POLL);
        return false;
    }
    let acts = s.watch_drag();
    s.tell(acts);
    true // a frame each refresh for the bob and the bubbles; the overlay is the glow's 140 pt while they're in
}

fn view(s: &Float, cx: &mut Cx<Float>) -> El {
    if s.hidden() {
        return el(); // nothing to see or click: the clear overlay passes everything to the app below
    }
    let back = ((s.t - s.hidden_until) / FADE_IN).clamp(0.0, 1.0) as f32; // 1 unless it just came back
    let dark = cx.system_dark();
    let still = cx.is_reduced_motion();
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let open = if s.link_over { 1.0 } else { s.openness() }; // a link held over it: lit as its target
    let size = (SMALL.0 + (BIG.0 - SMALL.0) * open, SMALL.1 + (BIG.1 - SMALL.1) * open);
    // Floats while idle; held still while dragged or open (the user is looking at it).
    let tucked = s.tuck.amount(s.t);
    let calm = still || s.dragging || tucked > 0.0;
    let bob = if calm { 0.0 } else { (s.t / 3.2 * std::f64::consts::TAU).sin() as f32 * (1.0 - open) };
    // the overlay's own points: the page's place on screen, less where the overlay is
    let [px, py, pw, ph] = s.drawn_rect(size);
    let (px, py) = (px - s.placed[0], py - s.placed[1] + 3.0 * bob);
    let (cx_, cy_) = (px + pw / 2.0, py + ph / 2.0);
    let halo = 46.0 + 18.0 * open;
    let glow = if dark { 0.32 + 0.16 * open } else { 0.2 + 0.12 * open };
    el().key("float").w_full().h_full().opacity(back)
        .child(el().key("halo").absolute(cx_ - halo, cy_ - halo).size(halo * 2.0, halo * 2.0)
            .radial_gradient([halo, halo], halo, [(0.0, blue.alpha(glow)), (1.0, blue.alpha(0.0))]))
        .children(menu(s, (cx_, cy_), still, dark))
        .child(paper((px, py), (pw, ph), bob, dark))
        .children(grip(s, (px, py, pw, ph), tucked, blue))
        // the badge stays on screen when the page's corner is tucked away
        .child(badge(s.badge, (corner(px + pw, s.placed[2]), corner(py, s.placed[3])), blue)
            .scale(if still { 1.0 } else { s.badge_scale() }))
}

/// A badge's centre kept inside an overlay this long (its own half and a point to spare).
fn corner(at: f32, length: f32) -> f32 {
    at.clamp(10.0, (length - 10.0).max(10.0))
}

/// `at` within `margin` points of `rect`.
fn near(rect: Rect, at: (f32, f32), margin: f32) -> bool {
    let [x, y, w, h] = rect;
    at.0 >= x - margin && at.0 <= x + w + margin && at.1 >= y - margin && at.1 <= y + h + margin
}

/// The grip on a tucked page's tab: a short blue bar along the strip still showing, fading in as it tucks.
fn grip(s: &Float, page: (f32, f32, f32, f32), tucked: f32, blue: Color) -> Option<El> {
    let edge = s.tuck.edge().filter(|_| tucked > 0.05)?;
    let (px, py, pw, ph) = page;
    let [dx, _, dw, _] = s.display();
    let left = dx - s.placed[0]; // the display's sides, in the overlay's points
    let right = left + dw;
    // the strip still showing, its middle: inside the side the page went past
    let strip = match edge {
        Edge::Left => px.max(left) + tuck::TAB / 2.0,
        Edge::Right => (px + pw).min(right) - tuck::TAB / 2.0,
    };
    let grip = el().key("grip").absolute(strip - 1.5, py + ph / 2.0 - 11.0).size(3.0, 22.0).radius(1.5);
    Some(grip.fill(blue).opacity(tucked.clamp(0.0, 1.0)))
}

/// The bubbles, flying out from the page's centre (`centre`, in the overlay) to their spots, or back. Only bubbles
/// on their way out or out take clicks; folding ones don't, and folded or not-yet-started ones aren't drawn at all, so
/// nothing invisible catches a click.
fn menu(s: &Float, centre: (f32, f32), still: bool, dark: bool) -> Vec<El> {
    let spots = s.spots();
    let home = (centre.0 - PILL.0 / 2.0, centre.1 - PILL.1 / 2.0);
    let menu = s.focus == Focus::Menu;
    let out = s.bubbles_out();
    s.items.iter().zip(spots).enumerate().filter_map(|(i, (bubble, spot))| {
        let k = if still { f32::from(u8::from(menu)) } else { out[i] };
        let to = (spot.0 - s.placed[0], spot.1 - s.placed[1]);
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
        .on_secondary_press(|s: &mut Float, _, _: &mut Tx| {
            let acts = s.right_click();
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
#[path = "float_tests.rs"]
mod tests;
