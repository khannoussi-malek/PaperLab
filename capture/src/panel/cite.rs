//! Cite: find a library paper as in Find, and Enter copies its reference (⌘↵ its BibTeX entry) for the document
//! being written; the panel then closes so the paste goes straight in.

use super::{Effect, Panel, Phase, Row};
use crate::api::{ApiError, Format};
use crate::library::matching;

impl Panel {
    pub(super) fn cite_rows(&self) -> Vec<Row> {
        if !self.reachable && self.papers.is_empty() {
            return vec![Row::OpenPaperLab];
        }
        matching(&self.papers, &self.query).into_iter().map(Row::Paper).collect()
    }

    pub(super) fn cite_submit(&mut self, format: Format) -> Vec<Effect> {
        match self.cite_rows().into_iter().nth(self.picked) {
            _ if self.phase == Phase::Copying => vec![],
            Some(Row::Paper(i)) => {
                self.seq += 1;
                self.phase = Phase::Copying;
                let paper = &self.papers[i];
                vec![Effect::Cite { seq: self.seq, paper_id: paper.id.clone(), title: paper.title.clone(), format }]
            }
            Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
            _ => vec![],
        }
    }

    /// The copy's answer, unless the user has since typed, switched mode or copied again.
    pub(super) fn copied(&mut self, seq: u64, what: String, result: Result<(), ApiError>) -> Vec<Effect> {
        if seq != self.seq || self.phase != Phase::Copying {
            return vec![];
        }
        match result {
            Ok(()) => {
                self.phase = Phase::Copied(format!("Copied {what}."));
                vec![Effect::CloseSoon(seq)]
            }
            Err(e) => {
                self.phase = self.failed(e);
                vec![]
            }
        }
    }

    pub(super) fn close_now(&self, seq: u64) -> Vec<Effect> {
        if seq == self.seq && matches!(self.phase, Phase::Copied(_)) { vec![Effect::Close] } else { vec![] }
    }
}
