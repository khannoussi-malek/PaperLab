//! The floating paper tucked into a screen's side: which side, and how far in it is at a moment. Let go against the
//! left or right edge (within SNAP), it slides in a moment after the last reason to be out, until only a TAB-wide
//! strip shows; a reason to be out (pointed at, opened, dragged, brought a file) slides it back, with a small
//! overshoot. Top and bottom are left alone: the menu bar and the Dock live there.

use crate::place::Edge;

/// The strip left showing, and how close to an edge a release tucks it, in points.
pub const TAB: f32 = 10.0;
pub const SNAP: f32 = 24.0;
/// How long a slide takes, and how long it waits after the last reason to be out before sliding in.
pub const SECONDS: f64 = 0.35;
pub const DELAY: f64 = 0.8;

#[derive(Clone, Copy, Debug)]
pub struct Tuck {
    edge: Option<Edge>,
    sliding_in: bool,
    /// When the current slide began, and how far in it was then (0 out, 1 in).
    since: f64,
    from: f32,
    /// When it last had a reason to be out.
    wanted_out_at: f64,
}

impl Tuck {
    /// Not tucked: free anywhere on screen.
    pub fn free() -> Self {
        Tuck { edge: None, sliding_in: false, since: f64::NEG_INFINITY, from: 0.0, wanted_out_at: 0.0 }
    }

    pub fn edge(&self) -> Option<Edge> {
        self.edge
    }

    /// How far into its edge at `t`: 0 out (all on screen) to 1 in. Sliding in eases; sliding out overshoots a
    /// touch past out and settles, so it pops back.
    pub fn amount(&self, t: f64) -> f32 {
        if self.edge.is_none() {
            return 0.0;
        }
        let k = ((t - self.since) / SECONDS).clamp(0.0, 1.0);
        let (target, curve) =
            if self.sliding_in { (1.0, k * k * (3.0 - 2.0 * k)) } else { (0.0, crate::bubbles::back_out(k)) };
        self.from + (target - self.from) * curve as f32
    }

    /// Let go at `t` against `edge` (None: away from every edge, so free). It stays out until its reason to be out
    /// (the pointer, just let go on it) has been gone a moment.
    pub fn snap(&mut self, edge: Option<Edge>, t: f64) {
        *self = Tuck { edge, since: t, wanted_out_at: t, ..Tuck::free() };
    }

    /// Taken off its edge (dragged away, its display gone).
    pub fn release(&mut self) {
        *self = Tuck::free();
    }

    /// A frame at `t`: with a reason to be out it slides out; a moment after the last one it slides in.
    pub fn watch(&mut self, t: f64, wanted_out: bool) {
        if self.edge.is_none() {
            return;
        }
        if wanted_out {
            self.wanted_out_at = t;
        }
        let sliding_in = t - self.wanted_out_at >= DELAY;
        if sliding_in != self.sliding_in {
            (self.from, self.sliding_in, self.since) = (self.amount(t), sliding_in, t);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn free_it_is_never_in() {
        let mut tuck = Tuck::free();
        tuck.watch(100.0, false);
        assert_eq!((tuck.edge(), tuck.amount(100.0)), (None, 0.0));
    }

    #[test]
    fn let_go_against_an_edge_it_waits_a_moment_then_slides_in() {
        let mut tuck = Tuck::free();
        tuck.snap(Some(Edge::Right), 10.0);
        tuck.watch(10.0 + DELAY / 2.0, false);
        assert_eq!(tuck.amount(10.0 + DELAY / 2.0), 0.0, "a moment first");
        tuck.watch(10.0 + DELAY, false);
        let half = tuck.amount(10.0 + DELAY + SECONDS / 2.0);
        assert!(half > 0.0 && half < 1.0, "{half}");
        assert_eq!(tuck.amount(10.0 + DELAY + SECONDS), 1.0);
    }

    #[test]
    fn a_reason_to_be_out_slides_it_back_from_where_it_is_with_an_overshoot() {
        let mut tuck = Tuck::free();
        tuck.snap(Some(Edge::Left), 0.0);
        tuck.watch(DELAY, false);
        let t = DELAY + SECONDS / 2.0;
        let midway = tuck.amount(t);
        tuck.watch(t, true);
        assert_eq!(tuck.amount(t), midway, "it turns from where it is: no jump");
        let lowest = (1..=20).map(|i| tuck.amount(t + SECONDS * f64::from(i) / 20.0)).fold(1.0, f32::min);
        assert!(lowest < 0.0, "past out a touch: {lowest}");
        assert_eq!(tuck.amount(t + SECONDS), 0.0, "and settled out");
    }

    #[test]
    fn released_it_is_free() {
        let mut tuck = Tuck::free();
        tuck.snap(Some(Edge::Right), 0.0);
        tuck.release();
        assert_eq!(tuck.edge(), None);
    }
}
