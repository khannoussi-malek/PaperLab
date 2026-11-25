//! The panel's behaviour as one state and one `step`: events in, effects out. No I/O here, so every path is tested
//! without a window or a server; `main.rs` performs the effects and feeds the answers back as events. Each mode's own
//! rules live in its module beside this one; this one holds the state and routes events to them.

mod find;
#[cfg(test)]
mod tests;

use crate::api::{Added, ApiError, Candidate, Found};
use crate::library::Paper;

#[derive(Clone, Debug, PartialEq)]
pub enum Phase {
    /// Local results for the query (newest papers when it's empty).
    Library,
    LookingUp(String),
    Found(Found),
    Adding(Candidate),
    /// The added paper and its latest status, until it's ready or failed.
    Added(Paper),
    NoFreePdf { candidate: Candidate, message: String },
    Failed(String),
}

#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    Shown,
    Closed,
    Query(String),
    Up,
    Down,
    Submit,
    Papers(Result<Vec<Paper>, ApiError>),
    Looked { seq: u64, result: Result<Found, ApiError> },
    AddDone(Result<Added, ApiError>),
    Status { id: String, result: Result<Paper, ApiError> },
}

#[derive(Clone, Debug, PartialEq)]
pub enum Effect {
    FetchPapers,
    Lookup { seq: u64, query: String },
    Add { candidate: Candidate, save_without_pdf: bool },
    /// Ask for the paper's status again in a second.
    Poll(String),
    Open(String),
    OpenPaperLab,
    Close,
}

/// What Enter acts on, in display order.
#[derive(Clone, Debug, PartialEq)]
pub enum Row {
    Paper(usize),
    SearchOnline(String),
    Candidate(usize),
    SaveWithoutPdf,
    OpenAdded(String),
    OpenPaperLab,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Panel {
    pub query: String,
    pub picked: usize,
    pub phase: Phase,
    pub papers: Vec<Paper>,
    /// False once a call found nothing listening; true again when one answers.
    pub reachable: bool,
    seq: u64,
    polling: Option<String>,
    /// Closed since it was last shown: an add finishing now is kept but not followed.
    hidden: bool,
}

impl Default for Panel {
    fn default() -> Self {
        Panel { query: String::new(), picked: 0, phase: Phase::Library, papers: vec![], reachable: true, seq: 0, polling: None, hidden: false }
    }
}

pub const UNREACHABLE: &str = "PaperLab isn't running. Open it, then try again.";

impl Panel {
    /// What Enter can act on now, in display order.
    pub fn rows(&self) -> Vec<Row> {
        self.find_rows()
    }

    pub fn step(&mut self, event: Event) -> Vec<Effect> {
        match event {
            Event::Shown => self.shown(),
            Event::Closed => self.closed(),
            Event::Query(q) => self.find_query(q),
            Event::Up => self.pick_by(-1),
            Event::Down => self.pick_by(1),
            Event::Submit => self.find_submit(),
            Event::Papers(result) => self.papers_arrived(result),
            Event::Looked { seq, result } => self.looked(seq, result),
            Event::AddDone(result) => self.add_done(result),
            Event::Status { id, result } => self.status(id, result),
        }
    }

    fn shown(&mut self) -> Vec<Effect> {
        *self = Panel { papers: std::mem::take(&mut self.papers), reachable: self.reachable, seq: self.seq, ..Panel::default() };
        vec![Effect::FetchPapers]
    }

    fn closed(&mut self) -> Vec<Effect> {
        self.polling = None;
        self.hidden = true;
        vec![]
    }

    /// Up (-1) or Down (+1), wrapping round the rows.
    fn pick_by(&mut self, delta: isize) -> Vec<Effect> {
        let n = self.rows().len();
        if n > 0 {
            self.picked = (self.picked as isize + delta).rem_euclid(n as isize) as usize;
        }
        vec![]
    }

    fn papers_arrived(&mut self, result: Result<Vec<Paper>, ApiError>) -> Vec<Effect> {
        match result {
            Ok(papers) => {
                self.papers = papers;
                self.reachable = true;
                self.clamp();
            }
            Err(e) => self.reachable = e != ApiError::Unreachable,
        }
        vec![]
    }

    fn failed(&mut self, e: ApiError) -> Phase {
        match e {
            ApiError::Unreachable => {
                self.reachable = false;
                Phase::Failed(UNREACHABLE.into())
            }
            ApiError::Said(sentence) => Phase::Failed(sentence),
        }
    }

    fn clamp(&mut self) {
        self.picked = self.picked.min(self.rows().len().saturating_sub(1));
    }
}
