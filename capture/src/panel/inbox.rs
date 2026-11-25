//! Inbox: what's new since the owner last looked, without opening PaperLab: free PDFs the weekly re-check found for
//! saved papers, and saved searches with new results. Enter opens the paper (and marks the find seen) or the
//! workspace's search.

use super::{Effect, Panel, Phase, Row};
use crate::mode::Mode;
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

    /// A fresh list, from opening Inbox or from the background refresh. The picked item stays picked; only while Inbox
    /// is on screen does the answer say whether PaperLab is up (in another mode the refresh runs unseen).
    pub(super) fn inbox_arrived(&mut self, result: Result<Inbox, ApiError>) -> Vec<Effect> {
        let on_screen = self.mode == Mode::Inbox;
        match result {
            Ok(inbox) => {
                let picked = self.picked_item();
                (self.inbox, self.inbox_error) = (Some(inbox), None);
                self.reachable |= on_screen;
                self.picked = self.inbox_rows().iter().position(|r| self.item(r) == picked && picked.is_some()).unwrap_or(0);
            }
            Err(ApiError::Unreachable) => self.reachable &= !on_screen,
            Err(ApiError::Said(sentence)) => {
                eprintln!("paperlab-capture: the Inbox couldn't be listed: {sentence}");
                self.inbox_error = Some(sentence); // the last list stays; the next refresh tries again
            }
        }
        vec![]
    }

    fn picked_item(&self) -> Option<String> {
        self.inbox_rows().get(self.picked).and_then(|r| self.item(r))
    }

    /// What a row is, across refreshes: the find's id, or the search's workspace and query.
    fn item(&self, row: &Row) -> Option<String> {
        let inbox = self.inbox.as_ref()?;
        match row {
            Row::FoundPdf(i) => inbox.found.get(*i).map(|f| f.id.clone()),
            Row::NewHits(i) => inbox.searches.get(*i).map(|s| format!("{}\n{}", s.workspace_id, s.query)),
            _ => None,
        }
    }
}
