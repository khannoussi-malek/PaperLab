//! Finding papers in the enabled sources and adding them to the library.

use serde::Deserialize;
use serde_json::{Value, json};

use super::{Api, ApiError, ok, said};
use crate::library::Paper;

/// A paper `/api/discovery/search` found. `raw` goes back to `/api/discovery/add` as it came.
#[derive(Clone, Debug, PartialEq)]
pub struct Candidate {
    pub title: String,
    pub authors: Vec<String>,
    pub year: Option<i32>,
    /// Set when the library already holds it.
    pub paper_id: Option<String>,
    pub raw: Value,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Found {
    pub results: Vec<Candidate>,
    /// Sources that failed, e.g. "Semantic Scholar is busy or unreachable."
    pub notices: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Added {
    Queued(Paper),
    AlreadyInLibrary(String),
    NoFreePdf(String),
}

impl Api {
    pub fn lookup(&self, query: &str) -> Result<Found, ApiError> {
        let url = format!("{}/api/discovery/search", self.base);
        let (status, body) = self.send(self.agent.get(&url).query("q", query).call())?;
        #[derive(Deserialize)]
        struct Out { results: Vec<Value>, #[serde(default)] notices: Vec<String> }
        let out: Out = ok(status, body)?;
        Ok(Found { results: out.results.into_iter().filter_map(candidate).collect(), notices: out.notices })
    }

    pub fn add(&self, candidate: &Candidate, save_without_pdf: bool) -> Result<Added, ApiError> {
        let url = format!("{}/api/discovery/add", self.base);
        let payload = json!({ "candidate": candidate.raw, "save_without_pdf": save_without_pdf });
        let (status, body) = self.send(self.agent.post(&url).send_json(&payload))?;
        if status == 409 {
            let error: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
            if let Some(id) = error.get("paper_id").and_then(Value::as_str) {
                return Ok(Added::AlreadyInLibrary(id.to_owned()));
            }
            if error.get("tried").is_some() || error.get("free_copies").is_some() {
                return Ok(Added::NoFreePdf(said(status, &error)));
            }
        }
        ok(status, body).map(Added::Queued)
    }
}

fn candidate(raw: Value) -> Option<Candidate> {
    let title = raw.get("title")?.as_str()?.to_owned();
    let authors = raw.get("authors").and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|n| n.as_str().map(str::to_owned)).collect()).unwrap_or_default();
    let year = raw.get("year").and_then(Value::as_i64).map(|y| y as i32);
    let paper_id = raw.get("paper_id").and_then(Value::as_str).map(str::to_owned);
    Some(Candidate { title, authors, year, paper_id, raw })
}
