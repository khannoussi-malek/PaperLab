//! The galaxy behind the panel: a click-through layer over the whole screen. When the panel opens, nebula light and
//! stars fade in, the star field turns slowly around the screen's centre, and papers drift out of the panel and fall
//! like leaves down the whole screen, swaying, fading near the end; then the stars settle to a dim, slow twinkle.
//! Everything is a pure function of the seconds since the panel opened, so it's unit-tested without a screen.

use rune::{Color, Cx, DisplayTarget, El, KeyPolicy, OverlayInput, OverlayOptions, OverlayPlacement, OverlaySpec, Tx, el};

const STARS: usize = 220;
const PAPERS: usize = 14;
/// Stars and nebula fade in over this long, then the stars stay bright until INTRO.
const FADE_IN: f64 = 2.0;
const INTRO: f64 = 4.0;
/// From the intro's brightness to the calm one.
const SETTLE: f64 = 2.0;
/// The star field turns once in this many seconds: slow enough to feel, never to watch.
const TURN: f64 = 600.0;
/// A paper's size in points.
const PAPER: (f32, f32) = (34.0, 44.0);
/// Where papers start: the panel's place (centred, 150 points from the top, about 60 points tall).
const PANEL_TOP: f32 = 150.0;
const PANEL_HEIGHT: f32 = 60.0;

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
    /// Polar position around the screen's centre: the field turns as one.
    angle: f32,
    distance: f32,
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
    /// Start offset from the panel's centre, and how far out it drifts (points, signed).
    x0: f32,
    drift: f32,
    /// Side-to-side sway: amplitude in points, period in seconds, phase.
    sway: f32,
    sway_period: f32,
    phase: f32,
    /// Its gentle rocking, in radians either way.
    rock: f32,
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
        // Out to the corners, so turning never leaves an empty corner.
        let reach = (size.0 * size.0 + size.1 * size.1).sqrt() / 2.0;
        let stars = (0..STARS)
            .map(|_| Star {
                angle: rng.unit() * std::f32::consts::TAU,
                distance: reach * rng.unit().sqrt(),
                radius: 0.6 + rng.unit() * 1.3,
                brightness: 0.4 + rng.unit() * 0.6,
                tint: match rng.unit() {
                    u if u < 0.72 => Tint::White,
                    u if u < 0.88 => Tint::Blue,
                    _ => Tint::Violet,
                },
                delay: f64::from(rng.unit()) * (FADE_IN - 0.8),
                period: 4.0 + f64::from(rng.unit()) * 5.0,
                phase: f64::from(rng.unit()) * std::f64::consts::TAU,
            })
            .collect();
        let papers = (0..PAPERS)
            .map(|i| {
                let side = if i % 2 == 0 { -1.0 } else { 1.0 };
                Flight {
                    x0: (rng.unit() - 0.5) * 420.0,
                    drift: side * (60.0 + rng.unit() * size.0 * 0.32),
                    sway: 18.0 + rng.unit() * 40.0,
                    sway_period: 2.4 + rng.unit() * 1.8,
                    phase: rng.unit() * std::f32::consts::TAU,
                    rock: 0.12 + rng.unit() * 0.25,
                    delay: f64::from(i as f32 * 0.22 + rng.unit() * 0.2),
                    life: 5.0 + f64::from(rng.unit()) * 2.0,
                }
            })
            .collect();
        Galaxy { size, visible: false, opened: None, t: 0.0, stars, papers }
    }

    /// The panel opened: start the intro on the next frame.
    pub fn open(&mut self) {
        if self.visible {
            return; // already open (the shortcut again): the sky goes on, no second intro
        }
        (self.visible, self.opened, self.t) = (true, None, 0.0);
    }

    pub fn close(&mut self) {
        self.visible = false;
    }

    /// How bright the nebula light is, 0 to 1.
    fn nebula(&self, still: bool) -> f32 {
        if still { 1.0 } else { ease((self.t / FADE_IN).min(1.0)) as f32 }
    }

    fn star(&self, s: &Star, still: bool) -> Sprite {
        let calm = 0.5 * s.brightness;
        let alpha = if still {
            calm
        } else {
            let fade_in = ease(((self.t - s.delay) / 0.8).clamp(0.0, 1.0)) as f32;
            let settle = ease(((self.t - INTRO) / SETTLE).clamp(0.0, 1.0)) as f32;
            let twinkle = 0.75 + 0.25 * ((self.t / s.period * std::f64::consts::TAU + s.phase).sin() as f32);
            fade_in * (s.brightness + (calm * twinkle - s.brightness) * settle)
        };
        let turned = if still { 0.0 } else { (self.t / TURN * std::f64::consts::TAU) as f32 };
        let (sin, cos) = (s.angle + turned).sin_cos();
        let (cx, cy) = (self.size.0 / 2.0, self.size.1 / 2.0);
        Sprite { x: cx + s.distance * cos, y: cy + s.distance * sin, alpha, rotation: 0.0 }
    }

    /// A paper in flight, or None before it starts and once it has faded.
    fn paper(&self, p: &Flight, still: bool) -> Option<Sprite> {
        let age = self.t - p.delay;
        if still || age < 0.0 || age >= p.life {
            return None;
        }
        // Falling leaves: out from the panel and down the whole screen, slowing their sideways drift, swaying and
        // rocking; a quick fade in, then a long fade over the last third.
        let k = (age / p.life) as f32;
        let a = age as f32;
        let start_y = PANEL_TOP + PANEL_HEIGHT;
        let fall = (self.size.1 - start_y + PAPER.1).max(0.0);
        let wave = (a / p.sway_period * std::f32::consts::TAU + p.phase).sin();
        let fade_in = (age / 0.4).min(1.0) as f32;
        let fade_out = (1.0 - ((k - 0.66) / 0.34).max(0.0)).max(0.0);
        Some(Sprite {
            x: self.size.0 / 2.0 + p.x0 + p.drift * (1.0 - (1.0 - k).powi(2)) + p.sway * wave,
            y: start_y + fall * (k * (0.35 + 0.65 * k)),
            alpha: (fade_in * fade_out).clamp(0.0, 1.0),
            rotation: p.rock * wave,
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

/// The galaxy's colours for the system's appearance: over dark windows white stars and pale pages; over light ones,
/// where white would vanish, stars in the brand's slate, blue and violet and pages with an edge and a firmer shadow.
#[derive(Clone, Copy, Debug, PartialEq)]
struct Palette {
    stars: [Color; 3],
    /// Nebula strength, blue then violet.
    nebula: (f32, f32),
    paper_edge: Color,
    paper_shadow: Color,
}

fn palette(dark: bool) -> Palette {
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let violet = rune::color::hex("#8b5cf6").expect("a valid colour");
    let slate = rune::color::hex("#475569").expect("a valid colour");
    if dark {
        Palette {
            stars: [Color::WHITE, blue.mix(Color::WHITE, 0.45), violet.mix(Color::WHITE, 0.45)],
            nebula: (0.16, 0.13),
            paper_edge: Color::TRANSPARENT,
            paper_shadow: Color::BLACK.alpha(0.25),
        }
    } else {
        Palette { stars: [slate, blue, violet], nebula: (0.12, 0.11), paper_edge: slate.alpha(0.25), paper_shadow: Color::BLACK.alpha(0.18) }
    }
}

fn view(g: &Galaxy, cx: &mut Cx<Galaxy>) -> El {
    let still = cx.is_reduced_motion();
    let colors = palette(cx.system_dark());
    let (w, h) = g.size;
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let violet = rune::color::hex("#8b5cf6").expect("a valid colour");
    let light = g.nebula(still);
    let (nb, nv) = colors.nebula;
    let mut root = el().key("galaxy").w_full().h_full()
        .child(el().key("nebula").absolute(0.0, 0.0).size(w, h)
            .radial_gradient([w * 0.22, h * 0.25], [w * 0.55, h * 0.6], [(0.0, blue.alpha(nb * light)), (1.0, blue.alpha(0.0))]))
        .child(el().key("nebula-violet").absolute(0.0, 0.0).size(w, h)
            .radial_gradient([w * 0.8, h * 0.78], [w * 0.5, h * 0.55], [(0.0, violet.alpha(nv * light)), (1.0, violet.alpha(0.0))]));
    for (i, s) in g.stars.iter().enumerate() {
        let at = g.star(s, still);
        let color = match s.tint {
            Tint::White => colors.stars[0],
            Tint::Blue => colors.stars[1],
            Tint::Violet => colors.stars[2],
        };
        let d = s.radius * 2.0;
        root = root.child(el().key(format!("star-{i}")).absolute(at.x - s.radius, at.y - s.radius).size(d, d)
            .radius(s.radius).fill(color.alpha(at.alpha)));
    }
    for (i, p) in g.papers.iter().enumerate() {
        if let Some(at) = g.paper(p, still) {
            root = root.child(paper_el(i, at, &colors));
        }
    }
    root
}

/// A page like the icon's: white, a few grey lines and one yellow highlight, with a soft shadow.
fn paper_el(i: usize, at: Sprite, colors: &Palette) -> El {
    let (w, h) = PAPER;
    let line = |top: f32, width: f32, color: Color| el().absolute(6.0, top).size(width, 2.5).radius(1.25).fill(color);
    let ink = Color::BLACK.alpha(0.28);
    let yellow = rune::color::hex("#facc15").expect("a valid colour");
    el().key(format!("paper-{i}")).absolute(at.x - w / 2.0, at.y - h / 2.0).size(w, h).radius(4.0)
        .fill(Color::WHITE.alpha(0.94)).border(1.0, colors.paper_edge).shadow(4.0, 10.0, colors.paper_shadow)
        .rotate(at.rotation).opacity(at.alpha)
        .child(line(9.0, 22.0, ink))
        .child(line(16.0, 22.0, yellow))
        .child(line(23.0, 22.0, ink))
        .child(line(30.0, 14.0, ink))
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
    fn papers_drift_for_seconds_then_are_gone() {
        let g = at(1.0);
        let flying: Vec<_> = g.papers.iter().filter_map(|p| g.paper(p, false)).collect();
        assert!(!flying.is_empty());
        assert!(flying.iter().all(|s| (0.0..=1.0).contains(&s.alpha)));
        let late = at(12.0);
        assert!(late.papers.iter().all(|p| late.paper(p, false).is_none()));
    }

    #[test]
    fn a_paper_falls_down_the_whole_screen_and_fades_near_the_end() {
        let p = Flight { x0: 0.0, drift: 200.0, sway: 30.0, sway_period: 3.0, phase: 0.0, rock: 0.2, delay: 0.0, life: 6.0 };
        let (early, mid, end) = (at(1.0).paper(&p, false).unwrap(), at(3.0).paper(&p, false).unwrap(), at(5.9).paper(&p, false).unwrap());
        assert!(early.y < mid.y && mid.y < end.y);
        assert!(end.y > 900.0 * 0.85, "it reaches the bottom of the screen");
        assert!(mid.alpha > 0.99 && end.alpha < 0.2, "it holds, then fades out at the end");
    }

    #[test]
    fn the_star_field_turns_slowly_and_reduce_motion_holds_it() {
        let star = at(0.0).stars[3];
        let (a, b) = (at(10.0).star(&star, false), at(20.0).star(&star, false));
        let moved = ((a.x - b.x).powi(2) + (a.y - b.y).powi(2)).sqrt();
        assert!(moved > 0.0 && moved < 200.0, "it moves, gently ({moved} points in 10 s)");
        assert_eq!(at(10.0).star(&star, true), at(20.0).star(&star, true));
    }

    #[test]
    fn stars_fade_in_then_settle_dimmer() {
        let star = Star { angle: 0.0, distance: 10.0, radius: 1.0, brightness: 0.8, tint: Tint::White, delay: 0.2, period: 4.0, phase: 0.0 };
        assert_eq!(at(0.0).star(&star, false).alpha, 0.0);
        let bright = at(1.0).star(&star, false).alpha;
        let calm = at(INTRO + SETTLE + 2.0).star(&star, false).alpha;
        assert!(bright > calm && calm > 0.0 && calm <= 0.8 * 0.5 + f32::EPSILON);
    }

    #[test]
    fn reduce_motion_holds_the_sky_still_without_papers() {
        let g = at(1.0);
        assert!(g.papers.iter().all(|p| g.paper(p, true).is_none()));
    }

    #[test]
    fn opening_an_open_galaxy_doesnt_replay_its_intro() {
        let mut g = at(3.0);
        g.opened = Some(10.0);
        g.open();
        assert_eq!((g.opened, g.t), (Some(10.0), 3.0));
    }

    #[test]
    fn light_mode_never_draws_white_stars_and_gives_pages_an_edge() {
        let (dark, light) = (palette(true), palette(false));
        assert_eq!(dark.stars[0], Color::WHITE);
        assert!(light.stars.iter().all(|c| c.luminance() < 0.5), "visible over white windows");
        assert!(light.paper_edge.a > 0.0 && dark.paper_edge.a == 0.0);
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
