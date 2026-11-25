//! What's new for the floating paper's Inbox: free PDFs the weekly re-check found, and saved searches with new results.

use serde::Deserialize;
use serde_json::json;

use super::{Api, ApiError, ok, refused};

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct FoundPdf {
    /// The find's own id, to mark it seen.
    pub id: String,
    pub paper_id: String,
    pub title: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
struct SavedSearch {
    query: String,
    new_hits: u32,
}

/// A saved search with results the owner hasn't looked at, and the workspace it runs in.
#[derive(Clone, Debug, PartialEq)]
pub struct NewHits {
    pub workspace_id: String,
    pub workspace: String,
    pub query: String,
    pub count: u32,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Inbox {
    pub found: Vec<FoundPdf>,
    pub searches: Vec<NewHits>,
}

impl Inbox {
    /// The things to look at: the floating paper's badge.
    pub fn count(&self) -> usize {
        self.found.len() + self.searches.len()
    }
}

impl Api {
    /// Everything new. ponytail: one request per workspace for its saved searches; fine for tens of workspaces
    /// every few minutes on localhost, a single endpoint if anyone has hundreds.
    pub fn inbox(&self) -> Result<Inbox, ApiError> {
        let (status, body) = self.send(self.agent.get(format!("{}/api/papers/found-pdfs", self.base)).call())?;
        let found = ok(status, body)?;
        let mut searches = vec![];
        for w in self.workspaces()? {
            let url = format!("{}/api/workspaces/{}/saved-searches", self.base, w.id);
            // One workspace failing (deleted meanwhile, say) leaves the rest of the Inbox and the badge.
            let saved: Vec<SavedSearch> = match self.send(self.agent.get(url).call()).and_then(|(s, b)| ok(s, b)) {
                Ok(saved) => saved,
                Err(e) => {
                    eprintln!("paperlab-capture: saved searches of workspace {} skipped: {e:?}", w.id);
                    continue;
                }
            };
            searches.extend(saved.into_iter().filter(|s| s.new_hits > 0).map(|s| NewHits {
                workspace_id: w.id.clone(), workspace: w.name.clone(), query: s.query, count: s.new_hits,
            }));
        }
        Ok(Inbox { found, searches })
    }

    /// The owner has opened this find: it leaves the Inbox (and PaperLab's own notice).
    pub fn found_seen(&self, id: &str) -> Result<(), ApiError> {
        let url = format!("{}/api/papers/found-pdfs/seen", self.base);
        let (status, body) = self.send(self.agent.post(url).send_json(json!({ "ids": [id] })))?;
        refused(status, &body)
    }
}
