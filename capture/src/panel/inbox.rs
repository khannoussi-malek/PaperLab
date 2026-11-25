//! Inbox: what's new since the owner last looked, without opening PaperLab: free PDFs the weekly re-check found for
//! saved papers, and saved searches with new results. Enter opens the paper (and marks the find seen) or the
//! workspace's search.

use super::{Effect, Panel, Phase, Row};
use crate::api::{ApiError, Inbox};

impl Panel {
    pub(super) fn inbox_rows(&self) -> Vec<Row> {
        match (&self.phase, &self.inbox) {
            (Phase::Failed(_), _) | (_, None) if !self.reachable => vec![Row::OpenPaperLab],
            (Phase::Library, Some(inbox)) => (0..inbox.found.len()).map(Row::FoundPdf)
                .chain((0..inbox.searches.len()).map(Row::NewHits)).collect(),
            _ => vec![],
        }
    }

    pub(super) fn inbox_submit(&mut self) -> Vec<Effect> {
        let Some(inbox) = &self.inbox else { return vec![] };
        match self.inbox_rows().into_iter().nth(self.picked) {
            Some(Row::FoundPdf(i)) => {
                let found = &inbox.found[i];
                vec![Effect::FoundSeen(found.id.clone()), Effect::Open(found.paper_id.clone()), Effect::Close]
            }
            Some(Row::NewHits(i)) => {
                vec![Effect::OpenWorkspace { id: inbox.searches[i].workspace_id.clone(), tab: "search" }, Effect::Close]
            }
            Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
            _ => vec![],
        }
    }

    pub(super) fn inbox_arrived(&mut self, result: Result<Inbox, ApiError>) -> Vec<Effect> {
        match result {
            Ok(inbox) => (self.inbox, self.reachable) = (Some(inbox), true),
            Err(ApiError::Unreachable) => self.reachable = false,
            Err(ApiError::Said(_)) => {} // the last list stays; the next refresh tries again
        }
        self.clamp();
        vec![]
    }
}
