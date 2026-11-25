//! "Has this been done?": the library papers closest to a pasted idea, each with its best passage.

use serde::Deserialize;
use serde_json::json;

use super::{Api, ApiError, ok};

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Close {
    pub paper_id: String,
    pub title: String,
    pub year: Option<i32>,
    /// "very close", "related" or "distant".
    pub label: String,
    pub passage: String,
    pub page: Option<i32>,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Closeness {
    pub papers: Vec<Close>,
    /// PaperLab's caveat: the library is only the owner's own, so nothing close is weak evidence of novelty.
    #[serde(default)]
    pub note: String,
}

impl Api {
    pub fn novelty(&self, text: &str) -> Result<Closeness, ApiError> {
        let url = format!("{}/api/novelty", self.base);
        let (status, body) = self.send(self.agent.post(&url).send_json(json!({ "text": text })))?;
        ok(status, body)
    }
}
