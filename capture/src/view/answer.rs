//! Ask's answer as it is written: wrapped text in a viewport that follows the end while it grows.

use rune::tok::type_;
use rune::{El, ScrollSpec, col, text};

use super::Ink;
use crate::panel::{Panel, Phase};

/// The answer's most height before it scrolls, in points.
const HEIGHT: f32 = 190.0;

pub(super) fn block(p: &Panel, ink: &Ink) -> Option<El> {
    let Phase::Answer(a) = &p.phase else { return None };
    if a.text.is_empty() {
        return None;
    }
    Some(col().key("answer").w_full().max_h(HEIGHT).px(18.0).pb(10.0).scroll(ScrollSpec { stick_bottom: true })
        .child(text(a.text.trim().to_owned()).font(type_::BODY).color(ink.text).wrap().w_full()))
}
