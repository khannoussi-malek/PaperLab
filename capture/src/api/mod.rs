//! PaperLab's REST API on 127.0.0.1, as Quick Capture calls it: the client and its error handling here, one module
//! per area beside it. Blocking: callers run them off the UI thread.

mod ask;
mod cite;
mod discovery;
mod library;
mod novelty;
mod upload;
#[cfg(test)]
mod tests;

pub use ask::{Said, Source, Workspace};
pub use cite::Format;
pub use discovery::{Added, Candidate, Found};
pub use novelty::{Close, Closeness};

use std::time::Duration;

use serde_json::Value;

#[derive(Clone, Debug, PartialEq)]
pub enum ApiError {
    /// Nothing answered: PaperLab's stack isn't running (or not on this port).
    Unreachable,
    /// PaperLab answered with an error; its own sentence when it gave one.
    Said(String),
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

    fn send(&self, sent: Result<ureq::http::Response<ureq::Body>, ureq::Error>) -> Result<(u16, Vec<u8>), ApiError> {
        let mut response = sent.map_err(not_sent)?;
        let status = response.status().as_u16();
        let body = response.body_mut().with_config().limit(64 << 20).read_to_vec().unwrap_or_default();
        Ok((status, body))
    }
}

/// Parses straight into `T`, skipping the fields it doesn't name: a 959-paper list is 2.1 MB of JSON, and a
/// `Value` tree of all of it held ~110 MB of the panel's footprint afterwards.
fn ok<T: serde::de::DeserializeOwned>(status: u16, body: Vec<u8>) -> Result<T, ApiError> {
    refused(status, &body)?;
    serde_json::from_slice(&body).map_err(|e| ApiError::Said(format!("PaperLab's answer didn't read as expected ({e}).")))
}

/// A request that got no answer: nothing listening, or listening but too slow (a busy source on a lookup or an add),
/// which is not "PaperLab isn't running"; anything else is said as it is.
fn not_sent(e: ureq::Error) -> ApiError {
    match e {
        ureq::Error::Timeout(_) => ApiError::Said("PaperLab didn't answer in time. Try again.".into()),
        ureq::Error::Io(_) | ureq::Error::ConnectionFailed | ureq::Error::HostNotFound => ApiError::Unreachable,
        other => ApiError::Said(format!("Couldn't reach PaperLab ({other}).")),
    }
}

/// A non-2xx answer as PaperLab's sentence for it.
fn refused(status: u16, body: &[u8]) -> Result<(), ApiError> {
    if (200..300).contains(&status) {
        return Ok(());
    }
    Err(ApiError::Said(said(status, &serde_json::from_slice(body).unwrap_or(Value::Null))))
}

/// PaperLab's errors carry a sentence in `detail`; a validation error carries a list instead.
fn said(status: u16, body: &Value) -> String {
    match body.get("detail").and_then(Value::as_str) {
        Some(sentence) => sentence.to_owned(),
        None => format!("PaperLab answered {status}."),
    }
}
