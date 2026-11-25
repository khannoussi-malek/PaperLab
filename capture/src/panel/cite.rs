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
            Some(Row::Paper(i)) => {
                let paper = &self.papers[i];
                vec![Effect::Cite { paper_id: paper.id.clone(), title: paper.title.clone(), format }]
            }
            Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
            _ => vec![],
        }
    }

    pub(super) fn cited(&mut self, title: String, format: Format, result: Result<(), ApiError>) -> Vec<Effect> {
        match result {
            Ok(()) => {
                self.phase = Phase::Copied(format!("Copied {} of “{title}”.", format.label()));
                vec![Effect::CloseSoon]
            }
            Err(e) => {
                self.phase = self.failed(e);
                vec![]
            }
        }
    }
}
