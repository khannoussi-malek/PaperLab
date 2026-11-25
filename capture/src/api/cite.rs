//! A library paper's reference, as PaperLab exports it: APA as plain text, or a BibTeX entry.

use super::{Api, ApiError, refused};
use serde_json::json;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Format {
    Apa,
    Bibtex,
}

impl Format {
    fn wire(self) -> &'static str {
        match self {
            Format::Apa => "apa",
            Format::Bibtex => "bibtex",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Format::Apa => "the APA reference",
            Format::Bibtex => "the BibTeX entry",
        }
    }
}

impl Api {
    pub fn cite(&self, paper_id: &str, format: Format) -> Result<String, ApiError> {
        let url = format!("{}/api/citations/export", self.base);
        let payload = json!({ "paper_ids": [paper_id], "format": format.wire() });
        let (status, body) = self.send(self.agent.post(&url).send_json(&payload))?;
        refused(status, &body)?;
        reference(&body)
    }
}

/// The exported text; nothing at all is an error, so an empty clipboard is never reported as "Copied".
pub(super) fn reference(body: &[u8]) -> Result<String, ApiError> {
    let text = String::from_utf8_lossy(body).trim().to_owned();
    if text.is_empty() {
        return Err(ApiError::Said("PaperLab gave no reference for this paper.".into()));
    }
    Ok(text)
}
