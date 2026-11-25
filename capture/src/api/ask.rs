//! Ask a workspace: its list, and a question answered from its papers, streamed as PaperLab writes it (server-sent
//! events: `sources`, then `token`s, then `done` or `error`).

use std::io::{BufRead, BufReader};

use serde::Deserialize;
use serde_json::{Value, json};

use super::{Api, ApiError, ok, refused};

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Workspace {
    pub id: String,
    pub name: String,
    pub paper_count: u32,
}

/// A passage the answer cites, by its marker ("C1").
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Source {
    pub label: String,
    pub paper_id: String,
    pub page: i32,
}

/// One step of an answer as it arrives.
#[derive(Clone, Debug, PartialEq)]
pub enum Said {
    Sources(Vec<Source>),
    Token(String),
    Done,
    /// PaperLab's sentence for what went wrong mid-answer.
    Failed(String),
}

impl Api {
    pub fn workspaces(&self) -> Result<Vec<Workspace>, ApiError> {
        let (status, body) = self.send(self.agent.get(format!("{}/api/workspaces", self.base)).call())?;
        ok(status, body)
    }

    /// Asks `question` of a workspace, calling `heard` with each step until the answer is done or fails.
    pub fn ask(&self, workspace_id: &str, question: &str, heard: impl FnMut(Said)) -> Result<(), ApiError> {
        let url = format!("{}/api/workspaces/{workspace_id}/chat", self.base);
        // A local model can take minutes over an answer: no overall limit on this one request.
        let request = self.agent.post(&url).config().timeout_global(None).build();
        let mut response = request.send_json(json!({ "question": question })).map_err(|_| ApiError::Unreachable)?;
        let status = response.status().as_u16();
        if !(200..300).contains(&status) {
            return refused(status, &response.body_mut().read_to_vec().unwrap_or_default());
        }
        read_events(BufReader::new(response.into_body().into_reader()), heard);
        Ok(())
    }
}

/// Reads server-sent events until the stream ends, `done` or `error`. Comments (pings) and unknown events are skipped;
/// a stream that ends without `done` is reported as cut off.
pub(super) fn read_events(reader: impl BufRead, mut heard: impl FnMut(Said)) {
    let (mut event, mut data) = (String::new(), String::new());
    for line in reader.lines() {
        let Ok(line) = line else { break };
        let line = line.trim_end_matches('\r');
        if let Some(name) = line.strip_prefix("event:") {
            event = name.trim().to_owned();
        } else if let Some(more) = line.strip_prefix("data:") {
            data.push_str(more.strip_prefix(' ').unwrap_or(more));
        } else if line.is_empty() && !event.is_empty() {
            let step = said_of(&event, &data);
            (event, data) = (String::new(), String::new());
            let Some(step) = step else { continue };
            let last = matches!(step, Said::Done | Said::Failed(_));
            heard(step);
            if last {
                return;
            }
        }
    }
    heard(Said::Failed("The answer was cut off. Try again.".into()));
}

fn said_of(event: &str, data: &str) -> Option<Said> {
    let value: Value = serde_json::from_str(data).ok()?;
    match event {
        "sources" => serde_json::from_value(value.get("sources")?.clone()).ok().map(Said::Sources),
        "token" => value.get("text")?.as_str().map(|t| Said::Token(t.to_owned())),
        "done" => Some(Said::Done),
        "error" => Some(Said::Failed(value.get("message")?.as_str()?.to_owned())),
        _ => None,
    }
}
