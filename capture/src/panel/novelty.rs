//! Done before?: paste an idea or an abstract, Enter asks the library for the closest papers (very close, related or
//! distant, each with its best passage); Enter on one opens it.

use super::{Effect, Panel, Phase, Row};
use crate::api::{ApiError, Closeness};

impl Panel {
    pub(super) fn novelty_rows(&self) -> Vec<Row> {
        match &self.phase {
            Phase::Close(found) => (0..found.papers.len()).map(Row::Close).collect(),
            Phase::Failed(_) if !self.reachable => vec![Row::OpenPaperLab],
            _ => vec![],
        }
    }

    pub(super) fn novelty_submit(&mut self) -> Vec<Effect> {
        match (self.novelty_rows().into_iter().nth(self.picked), &self.phase) {
            (Some(Row::Close(i)), Phase::Close(found)) => vec![Effect::Open(found.papers[i].paper_id.clone()), Effect::Close],
            (Some(Row::OpenPaperLab), _) => vec![Effect::OpenPaperLab, Effect::Close],
            (_, Phase::Searching) => vec![],
            _ if self.query.trim().is_empty() => vec![],
            _ => {
                self.seq += 1;
                self.phase = Phase::Searching;
                vec![Effect::Novelty { seq: self.seq, text: self.query.trim().to_owned() }]
            }
        }
    }

    pub(super) fn novelty(&mut self, seq: u64, result: Result<Closeness, ApiError>) -> Vec<Effect> {
        if seq != self.seq || !matches!(self.phase, Phase::Searching) {
            return vec![]; // another mode or a newer search made this answer stale
        }
        self.phase = match result {
            Ok(found) => Phase::Close(found),
            Err(e) => self.failed(e),
        };
        self.picked = 0;
        vec![]
    }
}
