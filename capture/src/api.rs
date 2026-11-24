//! The four PaperLab routes Quick Capture calls, on 127.0.0.1. Blocking: callers run them off the UI thread.

use std::time::Duration;

use serde::Deserialize;
use serde_json::{Value, json};

use crate::library::Paper;

#[derive(Clone, Debug, PartialEq)]
pub enum ApiError {
    /// Nothing answered: PaperLab's stack isn't running (or not on this port).
    Unreachable,
    /// PaperLab answered with an error; its own sentence when it gave one.
    Said(String),
}

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

#[derive(Clone)]
pub struct Api {
    base: String,
    agent: ureq::Agent,
}

impl Api {
    pub fn new(port: u16) -> Self {
        let config = ureq::Agent::config_builder()
            .http_status_as_error(false)
            // An online lookup asks every enabled source; a busy one can take 10 s or more.
            .timeout_global(Some(Duration::from_secs(60)))
            .build();
        Api { base: format!("http://127.0.0.1:{port}"), agent: ureq::Agent::new_with_config(config) }
    }

    pub fn papers(&self) -> Result<Vec<Paper>, ApiError> {
        let (status, body) = self.send(self.agent.get(&format!("{}/api/papers", self.base)).call())?;
        ok(status, body)
    }

    pub fn paper(&self, id: &str) -> Result<Paper, ApiError> {
        let (status, body) = self.send(self.agent.get(&format!("{}/api/papers/{id}", self.base)).call())?;
        ok(status, body)
    }

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

    fn send(&self, sent: Result<ureq::http::Response<ureq::Body>, ureq::Error>) -> Result<(u16, Vec<u8>), ApiError> {
        let mut response = sent.map_err(|_| ApiError::Unreachable)?;
        let status = response.status().as_u16();
        let body = response.body_mut().with_config().limit(64 << 20).read_to_vec().unwrap_or_default();
        Ok((status, body))
    }
}

/// Parses straight into `T`, skipping the fields it doesn't name: a 959-paper list is 2.1 MB of JSON, and a
/// `Value` tree of all of it held ~110 MB of the panel's footprint afterwards.
fn ok<T: serde::de::DeserializeOwned>(status: u16, body: Vec<u8>) -> Result<T, ApiError> {
    if !(200..300).contains(&status) {
        return Err(ApiError::Said(said(status, &serde_json::from_slice(&body).unwrap_or(Value::Null))));
    }
    serde_json::from_slice(&body).map_err(|e| ApiError::Said(format!("PaperLab's answer didn't read as expected ({e}).")))
}

/// PaperLab's errors carry a sentence in `detail`; a validation error carries a list instead.
fn said(status: u16, body: &Value) -> String {
    match body.get("detail").and_then(Value::as_str) {
        Some(sentence) => sentence.to_owned(),
        None => format!("PaperLab answered {status}."),
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::TcpListener;

    /// A one-request-per-connection fake PaperLab: `answer(method, path_and_query, body)` gives (status, json).
    fn fake(answer: impl Fn(&str, &str, &str) -> (u16, Value) + Send + 'static) -> Api {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let mut stream = stream.unwrap();
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let (mut line, mut length) = (String::new(), 0);
                reader.read_line(&mut line).unwrap();
                let mut parts = line.split_whitespace();
                let (method, target) = (parts.next().unwrap().to_owned(), parts.next().unwrap().to_owned());
                loop {
                    let mut header = String::new();
                    reader.read_line(&mut header).unwrap();
                    if header.trim().is_empty() { break; }
                    if let Some(v) = header.to_lowercase().strip_prefix("content-length:") { length = v.trim().parse().unwrap(); }
                }
                let mut body = vec![0; length];
                reader.read_exact(&mut body).unwrap();
                let (status, json) = answer(&method, &target, &String::from_utf8(body).unwrap());
                let json = json.to_string();
                write!(stream, "HTTP/1.1 {status} X\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{json}", json.len()).unwrap();
            }
        });
        Api::new(port)
    }

    fn paper_json(id: &str, status: &str) -> Value {
        json!({ "id": id, "title": "Attention Is All You Need", "authors": ["Ashish Vaswani"], "year": 2017,
                "doi": null, "status": status, "created_at": "2026-11-24T00:00:00Z", "abstract": "ignored" })
    }

    #[test]
    fn papers_and_one_paper() {
        let api = fake(|_, path, _| match path {
            "/api/papers" => (200, json!([paper_json("p1", "ready")])),
            "/api/papers/p1" => (200, paper_json("p1", "embedding")),
            _ => (404, json!({ "detail": "paper_not_found" })),
        });
        assert_eq!(api.papers().unwrap()[0].id, "p1");
        assert_eq!(api.paper("p1").unwrap().status, "embedding");
        assert_eq!(api.paper("nope"), Err(ApiError::Said("paper_not_found".into())));
    }

    #[test]
    fn lookup_sends_the_query_and_keeps_notices() {
        let api = fake(|_, path, _| {
            assert_eq!(path, "/api/discovery/search?q=10.48550%2FarXiv.1706.03762");
            (200, json!({ "results": [{ "title": "Attention", "authors": ["A B"], "year": 2017, "paper_id": "p9",
                                        "sources": ["arxiv"] }],
                          "notices": ["Semantic Scholar is busy or unreachable."] }))
        });
        let found = api.lookup("10.48550/arXiv.1706.03762").unwrap();
        assert_eq!(found.results[0].paper_id.as_deref(), Some("p9"));
        assert_eq!(found.results[0].raw["sources"], json!(["arxiv"]));
        assert_eq!(found.notices.len(), 1);
    }

    #[test]
    fn add_tells_queued_in_library_no_pdf_and_other_errors_apart() {
        let api = fake(|_, _, body| {
            let sent: Value = serde_json::from_str(body).unwrap();
            assert_eq!(sent["candidate"]["sources"], json!(["arxiv"]), "the candidate goes back as it came");
            match sent["candidate"]["title"].as_str().unwrap() {
                "new" if sent["save_without_pdf"] == json!(false) => (201, paper_json("p2", "uploaded")),
                "have" => (409, json!({ "detail": "This paper is already in your library.", "paper_id": "p1", "tried": [] })),
                "paywalled" => (409, json!({ "detail": "No free PDF was found for this paper.", "tried": [], "free_copies": [] })),
                _ => (409, json!({ "detail": "No paper source that can look this up is on." })),
            }
        });
        let c = |title: &str| Candidate { title: title.into(), authors: vec![], year: None, paper_id: None,
                                          raw: json!({ "title": title, "sources": ["arxiv"] }) };
        assert!(matches!(api.add(&c("new"), false), Ok(Added::Queued(p)) if p.id == "p2"));
        assert_eq!(api.add(&c("have"), false), Ok(Added::AlreadyInLibrary("p1".into())));
        assert_eq!(api.add(&c("paywalled"), false), Ok(Added::NoFreePdf("No free PDF was found for this paper.".into())));
        assert_eq!(api.add(&c("other"), false), Err(ApiError::Said("No paper source that can look this up is on.".into())));
    }

    #[test]
    fn nothing_listening_is_unreachable() {
        let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        assert_eq!(Api::new(port).papers(), Err(ApiError::Unreachable));
    }
}
