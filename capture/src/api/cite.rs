//! A library paper's reference, as PaperLab exports it: APA as plain text, or a BibTeX entry.

use super::{Api, ApiError, said};
use serde_json::{Value, json};

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
        if !(200..300).contains(&status) {
            return Err(ApiError::Said(said(status, &serde_json::from_slice(&body).unwrap_or(Value::Null))));
        }
        Ok(String::from_utf8_lossy(&body).trim().to_owned())
    }
}
