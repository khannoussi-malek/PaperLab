//! Note: write a thought down on a paper without leaving the app it came from. Find the paper as in Find, Enter, type
//! the note in the same field, Enter saves it to the paper (a note on the whole paper, as PaperLab's reader keeps
//! them) and the panel closes. A note being written survives the panel closing.

use super::{Effect, Panel, Phase, Row, UNREACHABLE};
use crate::api::ApiError;
use crate::library::matching;

/// The paper a note is being written on. The note itself is the field's text while it's on screen.
#[derive(Clone, Debug, PartialEq)]
pub struct Draft {
    pub paper_id: String,
    pub title: String,
    /// Why the last save didn't go through.
    pub error: Option<String>,
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
            Phase::Note(draft) if !self.query.trim().is_empty() => {
                self.seq += 1;
                let effect = Effect::SaveNote { seq: self.seq, paper_id: draft.paper_id.clone(), body: self.query.trim().to_owned() };
                self.phase = Phase::SavingNote(Draft { error: None, ..draft.clone() });
                vec![effect]
            }
            Phase::Library => match self.note_rows().into_iter().nth(self.picked) {
                Some(Row::Paper(i)) => {
                    let paper = &self.papers[i];
                    let draft = Draft { paper_id: paper.id.clone(), title: paper.title.clone(), error: None };
                    (self.phase, self.query, self.picked) = (Phase::Note(draft), String::new(), 0);
                    vec![]
                }
                Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
                _ => vec![],
            },
            _ => vec![],
        }
    }

    /// Typing: the note while one is being written (a save under way keeps its text), else the paper to find.
    pub(super) fn note_typed(&mut self, q: String) -> Vec<Effect> {
        match &self.phase {
            Phase::Note(_) | Phase::SavingNote(_) => {
                self.query = q;
                vec![]
            }
            _ => self.typed(q),
        }
    }

    /// The save's answer: saved closes the panel a moment later; otherwise the note stays, with why.
    pub(super) fn note_saved(&mut self, seq: u64, result: Result<(), ApiError>) -> Vec<Effect> {
        let Phase::SavingNote(draft) = &self.phase else { return vec![] };
        if seq != self.seq {
            return vec![];
        }
        let draft = draft.clone();
        match result {
            Ok(()) => {
                self.phase = Phase::NoteSaved(format!("Saved on “{}”.", draft.title));
                vec![Effect::CloseSoon(seq)]
            }
            Err(e) => {
                let error = match e {
                    ApiError::Unreachable => {
                        self.reachable = false;
                        UNREACHABLE.to_owned()
                    }
                    ApiError::Said(sentence) => sentence,
                };
                self.phase = Phase::Note(Draft { error: Some(error), ..draft });
                vec![]
            }
        }
    }
}
