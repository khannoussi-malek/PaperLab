//! Note: write a thought down on a paper without leaving the app it came from. Find the paper as in Find, Enter, type
//! the note in the same field, Enter saves it to the paper (a note on the whole paper, as PaperLab's reader keeps
//! them) and the panel closes.
//!
//! A note is never lost: whatever takes the panel out of Note (another mode, a drop, the panel reopening in another
//! mode from a bubble) sets it aside with its text, a save under way included, and coming back to Note brings it back.

use super::{Effect, Panel, Phase, Row, UNREACHABLE};
use crate::api::ApiError;
use crate::library::matching;
use crate::mode::Mode;

/// The most a note can hold (PaperLab's own limit).
const MAX_CHARS: usize = 50_000;

/// The paper a note is being written on. The note itself is the field's text while it's on screen.
#[derive(Clone, Debug, PartialEq)]
pub struct Draft {
    pub paper_id: String,
    pub title: String,
    /// Why the last save didn't go through, or why Enter didn't save.
    pub error: Option<String>,
    /// The save under way, to match its answer even after the panel moved on.
    seq: u64,
}

/// A note off screen: its phase (written, or being saved) and its text.
#[derive(Clone, Debug, PartialEq)]
pub struct Aside {
    phase: Phase,
    text: String,
}

impl Panel {
    /// What the field asks for: the mode's prompt, or the note itself once its paper is picked.
    pub fn placeholder(&self) -> &'static str {
        match self.phase {
            Phase::Note(_) | Phase::SavingNote(_) => "Write your note, then ↵",
            _ => self.mode.placeholder(),
        }
    }

    pub(super) fn note_rows(&self) -> Vec<Row> {
        match &self.phase {
            Phase::Library if !self.reachable && self.papers.is_empty() => vec![Row::OpenPaperLab],
            Phase::Library => matching(&self.papers, &self.query).into_iter().map(Row::Paper).collect(),
            _ => vec![],
        }
    }

    /// Enter: on a paper, start a note on it (the field empties for the note); on a note, save it.
    pub(super) fn note_submit(&mut self) -> Vec<Effect> {
        match &self.phase {
            Phase::Note(draft) => {
                let body = self.query.trim().to_owned();
                let refusal = match body.chars().count() {
                    0 => Some("Type the note first, then ↵ saves it.".to_owned()),
                    n if n > MAX_CHARS => Some(format!("A note holds up to {MAX_CHARS} characters; this one has {n}.")),
                    _ => None,
                };
                if let Some(error) = refusal {
                    self.phase = Phase::Note(Draft { error: Some(error), ..draft.clone() });
                    return vec![];
                }
                self.seq += 1;
                let draft = Draft { error: None, seq: self.seq, ..draft.clone() };
                let effect = Effect::SaveNote { seq: self.seq, paper_id: draft.paper_id.clone(), body };
                self.phase = Phase::SavingNote(draft);
                vec![effect]
            }
            Phase::Library => match self.note_rows().into_iter().nth(self.picked) {
                Some(Row::Paper(i)) => {
                    let paper = &self.papers[i];
                    let draft = Draft { paper_id: paper.id.clone(), title: paper.title.clone(), error: None, seq: 0 };
                    (self.phase, self.query, self.picked) = (Phase::Note(draft), String::new(), 0);
                    vec![]
                }
                Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
                _ => vec![],
            },
            _ => vec![],
        }
    }

    /// Typing: the note while one is being written (a save under way keeps its text; an edit clears the last error),
    /// else the paper to find.
    pub(super) fn note_typed(&mut self, q: String) -> Vec<Effect> {
        match &mut self.phase {
            Phase::Note(draft) => {
                draft.error = None;
                self.query = q;
                vec![]
            }
            Phase::SavingNote(_) => {
                self.query = q;
                vec![]
            }
            _ => self.typed(q),
        }
    }

    /// The save's answer, on screen or aside. Saved: on screen it says so and closes a moment later; aside it's done.
    /// Not saved: the note stays where it is, with why.
    pub(super) fn note_saved(&mut self, seq: u64, result: Result<(), ApiError>) -> Vec<Effect> {
        let on_screen = matches!(&self.phase, Phase::SavingNote(d) if d.seq == seq);
        let aside = matches!(&self.note_aside, Some(Aside { phase: Phase::SavingNote(d), .. }) if d.seq == seq);
        let draft = match (&self.phase, &self.note_aside) {
            (Phase::SavingNote(d), _) if on_screen => d.clone(),
            (_, Some(Aside { phase: Phase::SavingNote(d), .. })) if aside => d.clone(),
            _ => return vec![],
        };
        let error = match result {
            Ok(()) if on_screen => {
                (self.phase, self.query) = (Phase::NoteSaved(format!("Saved on “{}”.", draft.title)), String::new());
                return vec![Effect::CloseSoon(seq)];
            }
            Ok(()) => {
                self.note_aside = None;
                return vec![];
            }
            Err(ApiError::Unreachable) => {
                self.reachable = false;
                UNREACHABLE.to_owned()
            }
            Err(ApiError::Said(sentence)) => sentence,
        };
        let written = Phase::Note(Draft { error: Some(error), ..draft });
        match &mut self.note_aside {
            Some(parked) if aside => parked.phase = written,
            _ => self.phase = written,
        }
        vec![]
    }

    /// Leaving Note: the note on screen, if any, goes aside with its text (the field is then the next mode's).
    pub(super) fn set_note_aside(&mut self) {
        if matches!(self.phase, Phase::Note(_) | Phase::SavingNote(_)) {
            let phase = std::mem::replace(&mut self.phase, Phase::Library);
            self.note_aside = Some(Aside { phase, text: std::mem::take(&mut self.query) });
        }
    }

    /// In Note: a note set aside comes back, text and all.
    pub(super) fn bring_note_back(&mut self) {
        if self.mode == Mode::Note && let Some(Aside { phase, text }) = self.note_aside.take() {
            (self.phase, self.query, self.picked) = (phase, text, 0);
        }
    }
}
