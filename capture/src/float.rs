//! M79 spike (`--float`): a page that floats over every app, bottom right of the main display. Click it and a fan
//! of bubbles opens; Find and Add open the Quick Capture panel, the others are placeholders until the functions are
//! chosen and ranked. Throwaway: to feel the idea on screen, not the shipped design.

use rune::{
    Align, AppHandle, Color, Cx, DisplayTarget, El, KeyPolicy, OverlayInput, OverlayOptions, OverlayPlacement,
    OverlaySpec, ScreenEdge, Tx, el, text,
};

/// The overlay's size: room for the fan of bubbles above and left of the paper.
const SIZE: (f32, f32) = (320.0, 320.0);
const PAPER: (f32, f32) = (58.0, 74.0);
/// The paper's bottom-right corner sits this far in from the overlay's.
const INSET: f32 = 28.0;
const FAN_RADIUS: f32 = 128.0;
const BUBBLE: f32 = 46.0;

/// Glyph and name of each bubble, in fan order (from straight up to straight left).
const BUBBLES: [(&str, &str); 7] =
    [("⌕", "Find"), ("+", "Add"), ("?", "Ask"), ("❝", "Cite"), ("✓", "Check"), ("✎", "Idea"), ("★", "New")];

pub struct Float {
    me: AppHandle<crate::App>,
    /// Frame clock, seconds.
    t: f64,
    /// When the fan opened, or None while closed.
    opened: Option<f64>,
    /// A placeholder's "coming soon" line.
    note: Option<&'static str>,
}

impl Float {
    pub fn new(me: AppHandle<crate::App>) -> Self {
        Float { me, t: 0.0, opened: None, note: None }
    }

    fn toggle(&mut self) {
        self.opened = if self.opened.is_some() { None } else { Some(self.t) };
        self.note = None;
    }

    fn pick(&mut self, name: &'static str) {
        match name {
            "Find" | "Add" => {
                self.opened = None;
                crate::show(&self.me);
            }
            other => self.note = Some(other),
        }
    }
}

pub fn spec() -> rune::ConfiguredOverlay<Float> {
    let options = OverlayOptions {
        display: DisplayTarget::Primary,
        placement: Some(OverlayPlacement::Edge { edge: ScreenEdge::Bottom, margin: 12.0, align: Align::End, inset: 12.0 }),
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
    true // ponytail: frames every refresh for the bob; a still paper with a CSS-like loop when it ships
}

fn view(s: &Float, cx: &mut Cx<Float>) -> El {
    let dark = cx.system_dark();
    let still = cx.is_reduced_motion();
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let (pw, ph) = PAPER;
    let wave = if still { 0.0 } else { (s.t / 3.2 * std::f64::consts::TAU).sin() as f32 };
    let (px, py) = (SIZE.0 - INSET - pw, SIZE.1 - INSET - ph + 4.0 * wave);
    let centre = [px + pw / 2.0, py + ph / 2.0];

    let mut root = el().key("float").w_full().h_full()
        // A soft blue light around the paper, like the icon's.
        .child(el().key("halo").absolute(centre[0] - 70.0, centre[1] - 70.0).size(140.0, 140.0)
            .radial_gradient([70.0, 70.0], 70.0, [(0.0, blue.alpha(if dark { 0.35 } else { 0.22 })), (1.0, blue.alpha(0.0))]));

    if let Some(opened) = s.opened {
        let grow = ease(((s.t - opened) / 0.28).clamp(0.0, 1.0)) as f32;
        for (i, (glyph, name)) in BUBBLES.iter().enumerate() {
            let angle = std::f32::consts::FRAC_PI_2 * (1.0 + i as f32 / (BUBBLES.len() - 1) as f32);
            let r = FAN_RADIUS * grow;
            let (bx, by) = (centre[0] + r * angle.cos() - BUBBLE / 2.0, centre[1] - r * angle.sin() - BUBBLE / 2.0);
            root = root.child(bubble(i, glyph, name, (bx, by), dark).opacity(grow))
                .child(el().key(format!("label-{i}")).absolute(bx - 12.0, by + BUBBLE + 3.0).w(BUBBLE + 24.0).center()
                    .child(text((*name).to_owned()).font(rune::tok::type_::LABEL)
                        .color(if dark { Color::WHITE } else { Color::BLACK }.alpha(0.75)))
                    .opacity(grow));
        }
    }
    if let Some(name) = s.note {
        root = root.child(text(format!("{name}: coming soon")).key("note").font(rune::tok::type_::LABEL)
            .color(if dark { Color::WHITE } else { Color::BLACK }.alpha(0.8))
            .absolute(px - 150.0, py + ph - 14.0).w(140.0));
    }
    root.child(paper(px, py, wave, dark))
}

fn paper(x: f32, y: f32, wave: f32, dark: bool) -> El {
    let (w, h) = PAPER;
    let ink = Color::BLACK.alpha(0.28);
    let yellow = rune::color::hex("#facc15").expect("a valid colour");
    let slate = rune::color::hex("#475569").expect("a valid colour");
    let line = |top: f32, width: f32, color: Color| el().absolute(10.0, top).size(width, 3.5).radius(1.75).fill(color);
    el().key("paper").absolute(x, y).size(w, h).radius(6.0).fill(Color::WHITE.alpha(0.96))
        .border(1.0, if dark { Color::TRANSPARENT } else { slate.alpha(0.25) })
        .shadow(6.0, 16.0, Color::BLACK.alpha(if dark { 0.45 } else { 0.22 }))
        .rotate(0.05 * wave)
        .child(line(14.0, 38.0, ink))
        .child(line(24.0, 38.0, yellow))
        .child(line(34.0, 38.0, ink))
        .child(line(44.0, 26.0, ink))
        .hit()
        .on_press(|s: &mut Float| s.toggle())
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
