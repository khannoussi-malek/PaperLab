//! The panel's behaviour as one state and one `step`: events in, effects out. No I/O here, so every path is tested
//! without a window or a server; `main.rs` performs the effects and feeds the answers back as events. Each mode's own
//! rules live in its module beside this one; this one holds the state and routes events to them.

mod cite;
mod find;
mod novelty;
#[cfg(test)]
mod tests;

use crate::api::{Added, ApiError, Candidate, Closeness, Format, Found};
use crate::library::Paper;
use crate::mode::Mode;

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
    /// Cite: a reference is on the clipboard (the sentence saying which).
    Copied(String),
    /// Done before?: looking through the library for the idea.
    Searching,
    Close(Closeness),
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
    /// The mode bar: one mode, or the next/previous (Tab, ⇧Tab).
    Mode(Mode),
    NextMode { forward: bool },
    /// ⌘↵: the mode's second action (Cite: BibTeX instead of APA).
    SubmitAlt,
    Cited { title: String, format: Format, result: Result<(), ApiError> },
    Novelty { seq: u64, result: Result<Closeness, ApiError> },
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
    /// Close once the user has read a short confirmation.
    CloseSoon,
    /// Copy a library paper's reference to the clipboard.
    Cite { paper_id: String, title: String, format: Format },
    Novelty { seq: u64, text: String },
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
    /// A paper close to the idea (Done before?), by its place in the answer.
    Close(usize),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Panel {
    pub mode: Mode,
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
        Panel { mode: Mode::Find, query: String::new(), picked: 0, phase: Phase::Library, papers: vec![], reachable: true, seq: 0, polling: None, hidden: false }
    }
}

pub const UNREACHABLE: &str = "PaperLab isn't running. Open it, then try again.";

impl Panel {
    /// What Enter can act on now, in display order.
    pub fn rows(&self) -> Vec<Row> {
        match self.mode {
            Mode::Find => self.find_rows(),
            Mode::Cite => self.cite_rows(),
            Mode::Novelty => self.novelty_rows(),
        }
    }

    pub fn step(&mut self, event: Event) -> Vec<Effect> {
        match event {
            Event::Shown => self.shown(),
            Event::Closed => self.closed(),
            Event::Query(q) if self.mode == Mode::Find => self.find_query(q),
            Event::Query(q) => self.typed(q),
            Event::Up => self.pick_by(-1),
            Event::Down => self.pick_by(1),
            Event::Submit => self.submit(false),
            Event::SubmitAlt => self.submit(true),
            Event::Mode(mode) => self.set_mode(mode),
            Event::NextMode { forward } => self.set_mode(self.mode.step(forward)),
            Event::Cited { title, format, result } => self.cited(title, format, result),
            Event::Novelty { seq, result } => self.novelty(seq, result),
            Event::Papers(result) => self.papers_arrived(result),
            Event::Looked { seq, result } => self.looked(seq, result),
            Event::AddDone(result) => self.add_done(result),
            Event::Status { id, result } => self.status(id, result),
        }
    }

    fn shown(&mut self) -> Vec<Effect> {
        *self = Panel {
            mode: self.mode, papers: std::mem::take(&mut self.papers), reachable: self.reachable, seq: self.seq,
            ..Panel::default()
        };
        vec![Effect::FetchPapers]
    }

    /// Enter (or ⌘↵, `alt`): the mode's action on the picked row.
    fn submit(&mut self, alt: bool) -> Vec<Effect> {
        match self.mode {
            Mode::Find => self.find_submit(),
            Mode::Cite => self.cite_submit(if alt { Format::Bibtex } else { Format::Apa }),
            Mode::Novelty => self.novelty_submit(),
        }
    }

    /// Another mode: what was typed stays (find a paper, then cite it); the last answer goes.
    fn set_mode(&mut self, mode: Mode) -> Vec<Effect> {
        if matches!(self.phase, Phase::Adding(_)) {
            return vec![]; // an add in flight keeps Find until it answers
        }
        (self.mode, self.phase, self.picked, self.polling) = (mode, Phase::Library, 0, None);
        vec![]
    }

    /// Typing in a mode other than Find: the text is the query; an earlier answer, or one still coming, no longer
    /// matches it.
    fn typed(&mut self, q: String) -> Vec<Effect> {
        (self.query, self.picked, self.phase) = (q, 0, Phase::Library);
        vec![]
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
