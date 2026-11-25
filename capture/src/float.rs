//! M79 spike (`--float`): a small page floating over every app. Drag it anywhere; click it and it grows and a fan of
//! bubbles opens; Find and Add open the Quick Capture panel, the others are placeholders until the functions are
//! chosen and ranked. Throwaway: to feel the idea on screen, not the shipped design.

use rune::{
    AppHandle, Color, Cx, DisplayTarget, Drag, El, KeyPolicy, OverlayHandle, OverlayInput, OverlayOptions,
    OverlayPlacement, OverlaySpec, Phase, Tx, el, text,
};

/// The overlay's size: room for the open paper and the fan of bubbles above and left of it.
const SIZE: (f32, f32) = (320.0, 320.0);
/// The paper while idle, and opened.
const SMALL: (f32, f32) = (36.0, 46.0);
const BIG: (f32, f32) = (58.0, 74.0);
/// The paper's bottom-right corner sits this far in from the overlay's; it grows up and left from there.
const INSET: f32 = 28.0;
const FAN_RADIUS: f32 = 128.0;
const BUBBLE: f32 = 46.0;
/// A press that travels less than this is a click, not a drag (points).
const CLICK_SLOP: f32 = 4.0;
const GROW_SECONDS: f64 = 0.25;

/// Glyph and name of each bubble, in fan order (from straight up to straight left).
const BUBBLES: [(&str, &str); 7] =
    [("⌕", "Find"), ("+", "Add"), ("?", "Ask"), ("❝", "Cite"), ("✓", "Check"), ("✎", "Idea"), ("★", "New")];

pub struct Float {
    me: AppHandle<crate::App>,
    /// Its own overlay, to move it while dragged; set once created.
    pub handle: Option<OverlayHandle<Float>>,
    /// The overlay's top-left on the main display, in points.
    origin: (f32, f32),
    /// The origin at the press, while a drag is under way.
    grab: (f32, f32),
    dragging: bool,
    /// Frame clock, seconds.
    t: f64,
    open: bool,
    /// When it last opened or closed, for the grow and shrink.
    since: f64,
    /// A placeholder's "coming soon" line.
    note: Option<&'static str>,
}

impl Float {
    pub fn new(me: AppHandle<crate::App>, origin: (f32, f32)) -> Self {
        Float { me, handle: None, origin, grab: origin, dragging: false, t: 0.0, open: false, since: -1.0, note: None }
    }

    /// How open it is, 0 (small, no fan) to 1 (big, fan out), easing over GROW_SECONDS.
    fn openness(&self) -> f32 {
        let k = ease(((self.t - self.since) / GROW_SECONDS).clamp(0.0, 1.0)) as f32;
        if self.open { k } else { 1.0 - k }
    }

    fn toggle(&mut self) {
        // From where a half-finished grow or shrink is, so it reverses smoothly.
        let k = f64::from(self.openness());
        self.open = !self.open;
        self.since = self.t - GROW_SECONDS * if self.open { k } else { 1.0 - k };
        self.note = None;
    }

    /// Press, move, release on the paper: a press that barely moves is a click (open or close); otherwise the overlay
    /// follows the pointer. Rune reports pointer travel even while the window moves under it.
    fn drag(&mut self, d: &Drag) {
        match d.phase {
            Phase::Down => (self.grab, self.dragging) = (self.origin, false),
            Phase::Move => {
                if self.dragging || d.dx.hypot(d.dy) >= CLICK_SLOP {
                    self.dragging = true;
                    self.origin = (self.grab.0 + d.dx, self.grab.1 + d.dy);
                    if let Some(handle) = &self.handle {
                        handle.set_placement(Some(place(self.origin)));
                    }
                }
            }
            Phase::Up => {
                if !self.dragging && !d.cancelled() {
                    self.toggle();
                }
                self.dragging = false;
            }
        }
    }

    fn pick(&mut self, name: &'static str) {
        match name {
            "Find" | "Add" => {
                self.toggle();
                crate::show(&self.me);
            }
            other => self.note = Some(other),
        }
    }
}

fn place(origin: (f32, f32)) -> OverlayPlacement {
    OverlayPlacement::Rect { x: origin.0, y: origin.1, width: SIZE.0, height: SIZE.1 }
}

/// Where it starts: bottom right of a screen this size (points).
pub fn start(screen: (f32, f32)) -> (f32, f32) {
    (screen.0 - SIZE.0 - 12.0, screen.1 - SIZE.1 - 12.0)
}

pub fn spec(origin: (f32, f32)) -> rune::ConfiguredOverlay<Float> {
    let options = OverlayOptions {
        display: DisplayTarget::Primary,
        placement: Some(place(origin)),
        // Only the paper and its bubbles take clicks; the clear rest passes them to the app below.
        input: OverlayInput::Regions,
        keys: KeyPolicy::None,
        prewarm: true,
        ..Default::default()
    };
    OverlaySpec::new("PaperLab floating paper", SIZE, view).options(options).poll(poll)
}

fn poll(s: &mut Float, now: f64, _: &mut Tx) -> bool {
    s.t = now;
    true // ponytail: frames every refresh for the bob; a still paper with a looped animation when it ships
}

fn view(s: &Float, cx: &mut Cx<Float>) -> El {
    let dark = cx.system_dark();
    let still = cx.is_reduced_motion();
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let open = s.openness();
    let (pw, ph) = (SMALL.0 + (BIG.0 - SMALL.0) * open, SMALL.1 + (BIG.1 - SMALL.1) * open);
    let bob = if still || s.dragging { 0.0 } else { (s.t / 3.2 * std::f64::consts::TAU).sin() as f32 };
    let (px, py) = (SIZE.0 - INSET - pw, SIZE.1 - INSET - ph + 3.0 * bob);
    let centre = [px + pw / 2.0, py + ph / 2.0];
    let halo = 50.0 + 30.0 * open;

    let mut root = el().key("float").w_full().h_full()
        // A soft blue light around the paper, like the icon's; a little wider while open.
        .child(el().key("halo").absolute(centre[0] - halo, centre[1] - halo).size(halo * 2.0, halo * 2.0)
            .radial_gradient([halo, halo], halo, [(0.0, blue.alpha(if dark { 0.35 } else { 0.22 })), (1.0, blue.alpha(0.0))]));

    if open > 0.01 {
        for (i, (glyph, name)) in BUBBLES.iter().enumerate() {
            let angle = std::f32::consts::FRAC_PI_2 * (1.0 + i as f32 / (BUBBLES.len() - 1) as f32);
            let r = FAN_RADIUS * open;
            let (bx, by) = (centre[0] + r * angle.cos() - BUBBLE / 2.0, centre[1] - r * angle.sin() - BUBBLE / 2.0);
            root = root.child(bubble(i, glyph, name, (bx, by), dark).opacity(open))
                .child(el().key(format!("label-{i}")).absolute(bx - 12.0, by + BUBBLE + 3.0).w(BUBBLE + 24.0).center()
                    .child(text((*name).to_owned()).font(rune::tok::type_::LABEL)
                        .color(if dark { Color::WHITE } else { Color::BLACK }.alpha(0.75)))
                    .opacity(open));
        }
    }
    if let Some(name) = s.note {
        root = root.child(text(format!("{name}: coming soon")).key("note").font(rune::tok::type_::LABEL)
            .color(if dark { Color::WHITE } else { Color::BLACK }.alpha(0.8))
            .absolute(px - 150.0, py + ph - 14.0).w(140.0));
    }
    root.child(paper((px, py), (pw, ph), bob, dark))
}

/// The page, drawn at any size between SMALL and BIG: its lines scale with it.
fn paper(at: (f32, f32), size: (f32, f32), bob: f32, dark: bool) -> El {
    let (w, h) = size;
    let u = w / BIG.0; // 1 at full size
    let ink = Color::BLACK.alpha(0.28);
    let yellow = rune::color::hex("#facc15").expect("a valid colour");
    let slate = rune::color::hex("#475569").expect("a valid colour");
    let line = |top: f32, width: f32, color: Color| {
        el().absolute(10.0 * u, top * u).size(width * u, 3.5 * u).radius(1.75 * u).fill(color)
    };
    el().key("paper").absolute(at.0, at.1).size(w, h).radius(6.0 * u).fill(Color::WHITE.alpha(0.96))
        .border(1.0, if dark { Color::TRANSPARENT } else { slate.alpha(0.25) })
        .shadow(4.0 + 2.0 * u, 10.0 + 6.0 * u, Color::BLACK.alpha(if dark { 0.45 } else { 0.22 }))
        .rotate(0.05 * bob)
        .child(line(14.0, 38.0, ink))
        .child(line(24.0, 38.0, yellow))
        .child(line(34.0, 38.0, ink))
        .child(line(44.0, 26.0, ink))
        .hit()
        .on_drag(|s: &mut Float, d: &mut Drag, _: &mut Tx| s.drag(d))
}

fn bubble(i: usize, glyph: &str, name: &'static str, at: (f32, f32), dark: bool) -> El {
    let fill = if dark { Color::BLACK.alpha(0.55) } else { Color::WHITE.alpha(0.85) };
    let ink = if dark { Color::WHITE } else { Color::BLACK.alpha(0.85) };
    el().key(format!("bubble-{i}")).absolute(at.0, at.1).size(BUBBLE, BUBBLE).radius(BUBBLE / 2.0).fill(fill)
        .border(1.0, if dark { Color::WHITE.alpha(0.15) } else { Color::BLACK.alpha(0.1) })
        .shadow(3.0, 10.0, Color::BLACK.alpha(0.25))
        .center()
        .child(text(glyph.to_owned()).font(rune::tok::type_::BODY).color(ink))
        .hit()
        .on_press(move |s: &mut Float| s.pick(name))
}

fn ease(x: f64) -> f64 {
    x * x * (3.0 - 2.0 * x)
}
