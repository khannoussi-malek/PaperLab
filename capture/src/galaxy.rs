//! The galaxy behind the panel: a click-through layer over the whole screen. When the panel opens, nebula light and
//! stars fade in and a few papers fly out of the panel, fall and fade; then the stars settle to a dim, slow twinkle.
//! Everything is a pure function of the seconds since the panel opened, so it's unit-tested without a screen.

use rune::{Color, Cx, DisplayTarget, El, KeyPolicy, OverlayInput, OverlayOptions, OverlayPlacement, OverlaySpec, Tx, el};

const STARS: usize = 140;
const PAPERS: usize = 10;
/// The intro: stars and nebula fade in, papers fly and fade.
const INTRO: f64 = 1.5;
/// From the intro's brightness to the calm one.
const SETTLE: f64 = 0.8;
/// Where papers start: the panel's place (centred, 150 points from the top, about 60 points tall).
const PANEL_TOP: f32 = 150.0;
const PANEL_HEIGHT: f32 = 60.0;
const GRAVITY: f32 = 420.0;

pub struct Galaxy {
    /// Screen size in points.
    size: (f32, f32),
    visible: bool,
    /// Clock time the panel opened; set on the first frame after it does.
    opened: Option<f64>,
    /// Seconds since it opened.
    t: f64,
    stars: Vec<Star>,
    papers: Vec<Flight>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Star {
    x: f32,
    y: f32,
    radius: f32,
    brightness: f32,
    tint: Tint,
    /// When it starts fading in during the intro.
    delay: f64,
    /// Twinkle period and phase.
    period: f64,
    phase: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Tint {
    White,
    Blue,
    Violet,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Flight {
    /// Start offset from the panel's centre bottom, and velocity in points per second.
    x0: f32,
    vx: f32,
    vy: f32,
    spin: f32,
    delay: f64,
    life: f64,
}

/// A star or paper as drawn at one moment.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Sprite {
    pub x: f32,
    pub y: f32,
    pub alpha: f32,
    pub rotation: f32,
}

impl Galaxy {
    pub fn new(size: (f32, f32)) -> Self {
        let mut rng = Rng(0x5eed_7a9e_11ab);
        let stars = (0..STARS)
            .map(|_| Star {
                x: rng.unit() * size.0,
                y: rng.unit() * size.1,
                radius: 0.6 + rng.unit() * 1.3,
                brightness: 0.4 + rng.unit() * 0.6,
                tint: match rng.unit() {
                    u if u < 0.72 => Tint::White,
                    u if u < 0.88 => Tint::Blue,
                    _ => Tint::Violet,
                },
                delay: f64::from(rng.unit()) * 0.8,
                period: 3.0 + f64::from(rng.unit()) * 4.0,
                phase: f64::from(rng.unit()) * std::f64::consts::TAU,
            })
            .collect();
        let papers = (0..PAPERS)
            .map(|i| {
                let side = if i % 2 == 0 { -1.0 } else { 1.0 };
                Flight {
                    x0: (rng.unit() - 0.5) * 360.0,
                    vx: side * (40.0 + rng.unit() * 160.0),
                    vy: -(120.0 + rng.unit() * 180.0),
                    spin: (rng.unit() - 0.5) * 6.0,
                    delay: f64::from(rng.unit()) * 0.25,
                    life: 1.1 + f64::from(rng.unit()) * 0.4,
                }
            })
            .collect();
        Galaxy { size, visible: false, opened: None, t: 0.0, stars, papers }
    }

    /// The panel opened: start the intro on the next frame.
    pub fn open(&mut self) {
        (self.visible, self.opened, self.t) = (true, None, 0.0);
    }

    pub fn close(&mut self) {
        self.visible = false;
    }

    /// How bright the nebula light is, 0 to 1.
    fn nebula(&self, still: bool) -> f32 {
        if still { 1.0 } else { ease((self.t / 0.9).min(1.0)) as f32 }
    }

    fn star(&self, s: &Star, still: bool) -> Sprite {
        let calm = 0.5 * s.brightness;
        let alpha = if still {
            calm
        } else {
            let fade_in = ease(((self.t - s.delay) / 0.5).clamp(0.0, 1.0)) as f32;
            let settle = ease(((self.t - INTRO) / SETTLE).clamp(0.0, 1.0)) as f32;
            let twinkle = 0.75 + 0.25 * ((self.t / s.period * std::f64::consts::TAU + s.phase).sin() as f32);
            fade_in * (s.brightness + (calm * twinkle - s.brightness) * settle)
        };
        Sprite { x: s.x, y: s.y, alpha, rotation: 0.0 }
    }

    /// A paper in flight, or None before it starts and once it has faded.
    fn paper(&self, p: &Flight, still: bool) -> Option<Sprite> {
        let age = self.t - p.delay;
        if still || age < 0.0 || age >= p.life {
            return None;
        }
        let a = age as f32;
        let fade = 1.0 - (age / p.life).powi(2) as f32;
        Some(Sprite {
            x: self.size.0 / 2.0 + p.x0 + p.vx * a,
            y: PANEL_TOP + PANEL_HEIGHT + p.vy * a + 0.5 * GRAVITY * a * a,
            alpha: fade.clamp(0.0, 1.0),
            rotation: p.spin * a,
        })
    }
}

/// Every frame while shown: the clock since the panel opened. False (no frame) while hidden.
pub fn poll(g: &mut Galaxy, now: f64, _: &mut Tx) -> bool {
    if !g.visible {
        return false;
    }
    let opened = *g.opened.get_or_insert(now);
    g.t = now - opened;
    true
}

pub fn spec(size: (f32, f32)) -> rune::ConfiguredOverlay<Galaxy> {
    let options = OverlayOptions {
        display: DisplayTarget::Primary,
        placement: Some(OverlayPlacement::FullScreen),
        input: OverlayInput::None,
        keys: KeyPolicy::None,
        prewarm: true,
        ..Default::default()
    };
    OverlaySpec::new("PaperLab Quick Capture galaxy", size, view).options(options).macos_level(3).poll(poll)
}

fn view(g: &Galaxy, cx: &mut Cx<Galaxy>) -> El {
    let still = cx.is_reduced_motion();
    let (w, h) = g.size;
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let violet = rune::color::hex("#8b5cf6").expect("a valid colour");
    let light = g.nebula(still);
    let mut root = el().key("galaxy").w_full().h_full()
        .child(el().key("nebula").absolute(0.0, 0.0).size(w, h)
            .radial_gradient([w * 0.22, h * 0.25], [w * 0.55, h * 0.6], [(0.0, blue.alpha(0.16 * light)), (1.0, blue.alpha(0.0))]))
        .child(el().key("nebula-violet").absolute(0.0, 0.0).size(w, h)
            .radial_gradient([w * 0.8, h * 0.78], [w * 0.5, h * 0.55], [(0.0, violet.alpha(0.13 * light)), (1.0, violet.alpha(0.0))]));
    for (i, s) in g.stars.iter().enumerate() {
        let at = g.star(s, still);
        let color = match s.tint {
            Tint::White => Color::WHITE,
            Tint::Blue => blue.mix(Color::WHITE, 0.45),
            Tint::Violet => violet.mix(Color::WHITE, 0.45),
        };
        let d = s.radius * 2.0;
        root = root.child(el().key(format!("star-{i}")).absolute(at.x - s.radius, at.y - s.radius).size(d, d)
            .radius(s.radius).fill(color.alpha(at.alpha)));
    }
    for (i, p) in g.papers.iter().enumerate() {
        if let Some(at) = g.paper(p, still) {
            root = root.child(paper_el(i, at));
        }
    }
    root
}

/// A tiny page: white, with two lines and a yellow highlight, like the icon's.
fn paper_el(i: usize, at: Sprite) -> El {
    let (w, h) = (16.0, 21.0);
    let line = |top: f32, width: f32, color: Color| el().absolute(3.0, top).size(width, 1.5).radius(0.75).fill(color);
    let ink = Color::BLACK.alpha(0.35);
    let yellow = rune::color::hex("#facc15").expect("a valid colour");
    el().key(format!("paper-{i}")).absolute(at.x - w / 2.0, at.y - h / 2.0).size(w, h).radius(2.0)
        .fill(Color::WHITE.alpha(0.92)).rotate(at.rotation).opacity(at.alpha)
        .child(line(5.0, 10.0, ink))
        .child(line(9.0, 10.0, yellow))
        .child(line(13.0, 7.0, ink))
}

fn ease(x: f64) -> f64 {
    x * x * (3.0 - 2.0 * x)
}

/// A small deterministic generator: the same sky every time, no dependency.
struct Rng(u64);

impl Rng {
    fn unit(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((self.0 >> 40) as f32) / ((1u64 << 24) as f32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(t: f64) -> Galaxy {
        let mut g = Galaxy::new((1440.0, 900.0));
        g.open();
        g.t = t;
        g
    }

    #[test]
    fn papers_fly_out_during_the_intro_and_are_gone_after() {
        let g = at(0.3);
        let flying: Vec<_> = g.papers.iter().filter_map(|p| g.paper(p, false)).collect();
        assert!(!flying.is_empty());
        assert!(flying.iter().all(|s| (0.0..=1.0).contains(&s.alpha)));
        let late = at(INTRO + 0.5);
        assert!(late.papers.iter().all(|p| late.paper(p, false).is_none()));
    }

    #[test]
    fn papers_fall_and_fade() {
        let p = Flight { x0: 0.0, vx: 100.0, vy: -150.0, spin: 1.0, delay: 0.0, life: 1.4 };
        let (early, late) = (at(0.2).paper(&p, false).unwrap(), at(1.2).paper(&p, false).unwrap());
        assert!(late.y > early.y, "gravity wins over the throw");
        assert!(late.alpha < early.alpha, "it fades as it drops");
    }

    #[test]
    fn stars_fade_in_then_settle_dimmer() {
        let star = Star { x: 1.0, y: 1.0, radius: 1.0, brightness: 0.8, tint: Tint::White, delay: 0.2, period: 4.0, phase: 0.0 };
        assert_eq!(at(0.0).star(&star, false).alpha, 0.0);
        let bright = at(1.0).star(&star, false).alpha;
        let calm = at(INTRO + SETTLE + 2.0).star(&star, false).alpha;
        assert!(bright > calm && calm > 0.0 && calm <= 0.8 * 0.5 + f32::EPSILON);
    }

    #[test]
    fn reduce_motion_holds_the_sky_still_without_papers() {
        let g = at(0.3);
        assert!(g.papers.iter().all(|p| g.paper(p, true).is_none()));
        let star = g.stars[0];
        assert_eq!(at(0.3).star(&star, true), at(5.0).star(&star, true));
    }

    #[test]
    fn hidden_draws_no_frames() {
        let mut g = Galaxy::new((800.0, 600.0));
        let mut tx = Tx::default();
        assert!(!poll(&mut g, 1.0, &mut tx));
        g.open();
        assert!(poll(&mut g, 2.0, &mut tx) && g.t == 0.0);
        assert!(poll(&mut g, 2.5, &mut tx) && (g.t - 0.5).abs() < 1e-9);
        g.close();
        assert!(!poll(&mut g, 3.0, &mut tx));
    }
}
