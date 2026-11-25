//! A note on a whole paper, as PaperLab keeps it: linked to the paper, with no spot on a page.

use super::{Api, ApiError, refused};
use serde_json::json;

impl Api {
    pub fn note(&self, paper_id: &str, body: &str) -> Result<(), ApiError> {
        let url = format!("{}/api/notes", self.base);
        let payload = json!({ "paper_id": paper_id, "body": body });
        let (status, body) = self.send(self.agent.post(&url).send_json(&payload))?;
        refused(status, &body)
    }
}
