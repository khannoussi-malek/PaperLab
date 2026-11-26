//! The bubble menu (M79): a click on the floating paper fans PaperLab's functions out around it in a crescent, on the
//! side of the screen with room. They pop out one after another with a little overshoot and fold back faster than
//! they came, so the eye follows them but nobody waits. When the clipboard holds a DOI, an arXiv ID or a link, a
//! first, blue bubble offers to add that paper in one click. A right-click brings out the paper's own two: open
//! PaperLab, or hide the paper for an hour. This file is which bubbles there are, where they go and how they look;
//! float.rs decides when they show and carries out a pick.

use rune::tok;
use rune::{Color, El, row, text};

use crate::input::Input;
use crate::mode::{MODES, Mode};

/// What a bubble does.
#[derive(Clone, Debug, PartialEq)]
pub enum Bubble {
    /// Look up and add the paper the clipboard names: an `Input::Doi` or `Input::Arxiv`.
    Copied(Input),
    Mode(Mode),
    /// The right-click pair.
    OpenPaperLab,
    Hide,
}

/// What picking a bubble does.
#[derive(Clone, Debug, PartialEq)]
pub enum Pick {
    /// Open the panel in this mode, with this typed in (the copied paper's identifier, to look up in Find).
    Panel(Mode, Option<String>),
    OpenPaperLab,
    /// Hide the floating paper for a while.
    Hide,
}

impl Bubble {
    pub fn pick(&self) -> Pick {
        match self {
            Bubble::Mode(mode) => Pick::Panel(*mode, None),
            Bubble::Copied(input) => Pick::Panel(Mode::Find, input.lookup().map(str::to_owned)),
            Bubble::OpenPaperLab => Pick::OpenPaperLab,
            Bubble::Hide => Pick::Hide,
        }
    }

    fn label(&self, waiting: usize) -> String {
        match self {
            Bubble::Mode(mode) => crate::view::pill_label(*mode, waiting),
            Bubble::Copied(Input::Arxiv(_)) => "Add copied arXiv".to_owned(),
            Bubble::Copied(Input::Link(_)) => "Add copied link".to_owned(),
            Bubble::Copied(_) => "Add copied DOI".to_owned(),
            Bubble::OpenPaperLab => "Open PaperLab".to_owned(),
            Bubble::Hide => "Hide for an hour".to_owned(),
        }
    }
}

/// The right-click bubbles: the paper's own actions, with the clipboard's link first when there is one (any web
/// link: a right-click is asked for, so a copied page can't be noise there).
pub fn paper_menu(copied_link: Option<String>) -> Vec<Bubble> {
    let link = copied_link.map(|link| Bubble::Copied(Input::Link(link)));
    link.into_iter().chain([Bubble::OpenPaperLab, Bubble::Hide]).collect()
}

/// The most bubbles there can be: the modes and the clipboard's paper.
pub const MAX: usize = MODES.len() + 1;
/// One bubble: a pill wide enough for "Done before?" and an Inbox count.
pub const PILL: (f32, f32) = (132.0, 34.0);
/// The crescent: bubbles a row apart, their inner edges on a circle of RADIUS round the page's centre.
const ROW: f32 = PILL.1 + 8.0;
const RADIUS: f32 = 150.0;
const MARGIN: f32 = 8.0;
/// The pop: each bubble starts this long after the one before and takes POP to land; the fold takes FOLD.
const STAGGER: f64 = 0.04;
const POP: f64 = 0.3;
const FOLD: f64 = 0.16;

/// The bubbles, top to bottom: the clipboard's paper first when there is one, then the modes.
pub fn menu(copied: Option<Input>) -> Vec<Bubble> {
    copied.map(Bubble::Copied).into_iter().chain(MODES.map(Bubble::Mode)).collect()
}

/// Each of `n` bubbles' top-left on screen for a page centred at `centre`: a crescent on the side with more room,
/// moved up or down as a whole so it stays on a screen this size. The first bubble is the top one.
pub fn spots(centre: (f32, f32), screen: (f32, f32), n: usize) -> Vec<(f32, f32)> {
    let side = if centre.0 > screen.0 / 2.0 { -1.0 } else { 1.0 };
    let arc: Vec<(f32, f32)> = (0..n).map(|i| {
        let dy = (i as f32 - (n as f32 - 1.0) / 2.0) * ROW;
        let inner = centre.0 + side * (RADIUS * RADIUS - dy * dy).sqrt(); // the edge nearest the page
        let x = if side < 0.0 { inner - PILL.0 } else { inner };
        (x, centre.1 + dy - PILL.1 / 2.0)
    }).collect();
    let (Some(first), Some(last)) = (arc.first(), arc.last()) else { return arc };
    let (top, bottom) = (first.1, last.1 + PILL.1);
    let shift = (MARGIN - top).max(0.0) + (screen.1 - MARGIN - bottom).min(0.0);
    arc.into_iter().map(|(x, y)| (x, y + shift)).collect()
}

/// How far out bubble `i` of `n` is, `since` seconds after the menu opened (`open`) or closed, starting `from` where it
/// was then: 0 at the page, 1 in place. On the way out it overshoots a little and settles; the fold runs bottom first
/// and doesn't bounce.
pub fn progress(since: f64, i: usize, n: usize, open: bool, from: f32) -> f32 {
    if open {
        let k = back_out(((since - i as f64 * STAGGER) / POP).clamp(0.0, 1.0)) as f32;
        from + (1.0 - from) * k
    } else {
        let k = ((since - n.saturating_sub(i + 1) as f64 * STAGGER / 2.0) / FOLD).clamp(0.0, 1.0);
        from * (1.0 - (k * k * (3.0 - 2.0 * k)) as f32)
    }
}

/// Overshoots about 8% and comes back: the pop.
pub(crate) fn back_out(x: f64) -> f64 {
    const C1: f64 = 1.4;
    let x = x - 1.0;
    1.0 + (C1 + 1.0) * x * x * x + C1 * x * x
}

/// A bubble's fill, text and hover colours (the hover is drawn over the fill). A mode's text is the logo's blue on a
/// light card and a light blue on a dark one (the logo's blue is too dark to read there); under the pointer it turns
/// white on the logo's blue. The clipboard's paper is white on the logo's blue, a little darker under the pointer.
fn colors(bubble: &Bubble, dark: bool) -> (Color, Color, Color) {
    let blue = rune::color::hex("#2664ee").expect("a valid colour");
    let light_blue = rune::color::hex("#a9c1ff").expect("a valid colour");
    match bubble {
        Bubble::Mode(_) | Bubble::OpenPaperLab | Bubble::Hide => {
            (tok::theme(dark).card.alpha(0.97), if dark { light_blue } else { blue }, blue)
        }
        Bubble::Copied(_) => (blue, Color::WHITE, Color::BLACK.alpha(0.18)),
    }
}

/// One bubble `k` of the way out (see `progress`), keyed `bubble-{i}`. A mode is its label in the logo's blue on the
/// theme's card colour, turning blue with white text under the pointer; the clipboard's paper is the other way round,
/// the suggestion that stands out.
pub fn pill(i: usize, bubble: &Bubble, waiting: usize, dark: bool, k: f32) -> El {
    let t = tok::theme(dark);
    let (fill, ink, hover) = colors(bubble, dark);
    let label = bubble.label(waiting);
    row().key(format!("bubble-{i}")).size(PILL.0, PILL.1).radius(PILL.1 / 2.0).center()
        .fill(fill)
        .border(1.0, if dark { Color::WHITE.alpha(0.12) } else { t.separator })
        .shadow(2.0, 10.0, Color::BLACK.alpha(if dark { 0.4 } else { 0.16 }))
        .hover(hover).hover_group()
        .opacity(k.clamp(0.0, 1.0))
        .scale(0.55 + 0.45 * k)
        .child(text(label).font(rune::TextStyle::new(13.0, 600.0)).color(ink).group_color(Color::WHITE))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// How far a bubble can sit from the page's centre (x, y), with the crescent pushed up or down to stay on screen.
    const REACH: (f32, f32) = (RADIUS + PILL.0 + MARGIN, 268.0);

    const SCREEN: (f32, f32) = (1440.0, 900.0);
    /// When the last bubble has landed.
    pub const SETTLED: f64 = (MAX - 1) as f64 * STAGGER + POP;

    fn overlaps(a: (f32, f32, f32, f32), b: (f32, f32, f32, f32)) -> bool {
        a.0 < b.0 + b.2 && b.0 < a.0 + a.2 && a.1 < b.1 + b.3 && b.1 < a.1 + a.3
    }

    /// Page centres from corner to corner, as far as a drag lets the page go (its half size from each edge).
    fn centres() -> impl Iterator<Item = (f32, f32)> {
        (0..=24).flat_map(|i| (0..=15).map(move |j| (22.0 + i as f32 * 58.0, 28.0 + j as f32 * 56.2)))
    }

    #[test]
    fn the_bubbles_fan_out_on_the_side_with_room() {
        let right = spots((1350.0, 450.0), SCREEN, 5);
        assert!(right.iter().all(|&(x, _)| x + PILL.0 < 1350.0), "a page on the right fans left");
        let left = spots((90.0, 450.0), SCREEN, 5);
        assert!(left.iter().all(|&(x, _)| x > 90.0), "a page on the left fans right");
        assert!(left[2].0 > left[0].0 && left[2].0 > left[4].0, "a crescent: the middle one reaches furthest");
    }

    #[test]
    fn every_bubble_stays_on_screen_inside_the_overlay_and_clear_of_the_page_and_each_other() {
        for (c, n) in centres().flat_map(|c| [(c, MAX - 1), (c, MAX)]) {
            let bubbles: Vec<_> = spots(c, SCREEN, n).into_iter().map(|(x, y)| (x, y, PILL.0, PILL.1)).collect();
            assert_eq!(bubbles.len(), n);
            let page = (c.0 - 22.0, c.1 - 28.0, 44.0, 56.0);
            for (i, &b) in bubbles.iter().enumerate() {
                let on_screen = b.0 >= MARGIN && b.1 >= MARGIN
                    && b.0 + b.2 <= SCREEN.0 - MARGIN && b.1 + b.3 <= SCREEN.1 - MARGIN;
                assert!(on_screen, "bubble {i} off screen for a page at {c:?}: {b:?}");
                let inside = (b.0 - c.0).abs().max((b.0 + b.2 - c.0).abs()) <= REACH.0
                    && (b.1 - c.1).abs().max((b.1 + b.3 - c.1).abs()) <= REACH.1;
                assert!(inside, "bubble {i} outside the overlay at {c:?}");
                assert!(!overlaps(b, page), "bubble {i} covers the page at {c:?}");
                for (j, &other) in bubbles.iter().enumerate().skip(i + 1) {
                    assert!(!overlaps(b, other), "bubbles {i} and {j} overlap at {c:?}");
                }
            }
        }
    }

    #[test]
    fn the_bubbles_pop_out_in_turn_overshoot_and_fold_back() {
        assert_eq!(progress(0.0, 0, MAX, true, 0.0), 0.0);
        let (first, second) = (progress(STAGGER, 0, MAX, true, 0.0), progress(STAGGER, 1, MAX, true, 0.0));
        assert!(first > 0.0 && second == 0.0, "one after another");
        let peak = (0..30).map(|n| progress(n as f64 * 0.01, 0, MAX, true, 0.0)).fold(0.0, f32::max);
        assert!(peak > 1.02 && peak < 1.12, "a small overshoot, not a wobble: {peak}");
        assert!((0..MAX).all(|i| progress(SETTLED, i, MAX, true, 0.0) == 1.0), "all landed by SETTLED");
        let quick = |i| progress(0.0, i, MAX, false, 1.0) == 1.0 && progress(0.3, i, MAX, false, 1.0) == 0.0;
        assert!((0..MAX).all(quick), "the fold is quick");
        assert_eq!(progress(0.0, 2, MAX, false, 0.4), 0.4, "a fold starts where the bubble is");
        assert_eq!(progress(0.0, 2, MAX, true, 0.4), 0.4, "so does a pop");
    }

    /// WCAG contrast between two opaque colours (rune's colours are linear, so `luminance` is WCAG's).
    fn contrast(a: Color, b: Color) -> f32 {
        let (la, lb) = (a.luminance(), b.luminance());
        (la.max(lb) + 0.05) / (la.min(lb) + 0.05)
    }

    /// `top` drawn over the opaque `bottom`.
    fn over(top: Color, bottom: Color) -> Color {
        bottom.mix(Color { a: 1.0, ..top }, top.a)
    }

    #[test]
    fn every_bubbles_text_reads_on_its_fill_in_light_and_dark_and_under_the_pointer() {
        let bubbles = [Bubble::Mode(Mode::Ask), Bubble::Hide, Bubble::Copied(Input::Doi("10.1234/x".into()))];
        for dark in [false, true] {
            for bubble in &bubbles {
                let (fill, ink, hover) = colors(bubble, dark);
                let fill = fill.alpha(1.0);
                let at_rest = contrast(ink, fill);
                assert!(at_rest >= 4.5, "{bubble:?} dark={dark}: {at_rest:.1}");
                let pointed = contrast(Color::WHITE, over(hover, fill)); // the text turns white under the pointer
                assert!(pointed >= 4.5, "{bubble:?} dark={dark}, pointed at: {pointed:.1}");
            }
        }
    }

    #[test]
    fn the_clipboard_paper_comes_first_and_only_when_there_is_one() {
        assert_eq!(menu(None), MODES.map(Bubble::Mode).to_vec());
        let doi = Input::Doi("10.1234/x".into());
        let with = menu(Some(doi.clone()));
        assert_eq!((with.len(), &with[0]), (MAX, &Bubble::Copied(doi)));
        assert_eq!(with[0].pick(), Pick::Panel(Mode::Find, Some("10.1234/x".to_owned())));
        assert_eq!(with[1].pick(), Pick::Panel(Mode::Find, None));
        assert_eq!(paper_menu(None).iter().map(Bubble::pick).collect::<Vec<_>>(), [Pick::OpenPaperLab, Pick::Hide]);
        assert_eq!(with[0].label(0), "Add copied DOI");
        let right = paper_menu(Some("https://example.org/a.pdf".into()));
        assert_eq!(right[0].pick(), Pick::Panel(Mode::Find, Some("https://example.org/a.pdf".to_owned())));
        assert_eq!(right[0].label(0), "Add copied link");
        assert_eq!(Bubble::Copied(Input::Arxiv("1706.03762".into())).label(0), "Add copied arXiv");
    }
}
