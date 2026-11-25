//! The panel's behaviour as one state and one `step`: events in, effects out. No I/O here, so every path is tested
//! without a window or a server; `main.rs` performs the effects and feeds the answers back as events. Each mode's own
//! rules live in its module beside this one; this one holds the state and routes events to them.

mod ask;
mod cite;
mod find;
mod novelty;
#[cfg(test)]
mod tests;

pub use ask::{Answer, Writing};

use crate::api::{Added, ApiError, Candidate, Closeness, Format, Found, Said, Workspace};
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
    /// A copy under way (Enter again waits for it).
    Copying,
    Copied(String),
    /// Done before?: looking through the library for the idea.
    Searching,
    Close(Closeness),
    /// Ask: an answer being written, or written.
    Answer(Answer),
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
    AddDone { seq: u64, result: Result<Added, ApiError> },
    Status { id: String, result: Result<Paper, ApiError> },
    /// The mode bar: one mode, or the next/previous (Tab, ⇧Tab).
    Mode(Mode),
    NextMode { forward: bool },
    /// ⌘↵: the mode's second action (Cite: BibTeX instead of APA).
    SubmitAlt,
    /// Something reached the clipboard (`what`: "the APA reference of “…”"), or didn't.
    Copied { seq: u64, what: String, result: Result<(), ApiError> },
    /// A moment after a copy: close if "Copied …" is still what the panel shows.
    CloseNow(u64),
    Novelty { seq: u64, result: Result<Closeness, ApiError> },
    Workspaces(Result<Vec<Workspace>, ApiError>),
    /// One step of an answer as PaperLab writes it; an error before the first.
    Heard { seq: u64, result: Result<Said, ApiError> },
}

#[derive(Clone, Debug, PartialEq)]
pub enum Effect {
    FetchPapers,
    Lookup { seq: u64, query: String },
    Add { seq: u64, candidate: Candidate, save_without_pdf: bool },
    /// Ask for the paper's status again in a second.
    Poll(String),
    Open(String),
    OpenPaperLab,
    Close,
    /// Send `CloseNow` back in a moment, once the user has read the confirmation.
    CloseSoon(u64),
    /// Copy a library paper's reference to the clipboard.
    Cite { seq: u64, paper_id: String, title: String, format: Format },
    Novelty { seq: u64, text: String },
    FetchWorkspaces,
    Ask { seq: u64, workspace_id: String, question: String },
    /// The workspace's chat in PaperLab, where the answer is saved.
    OpenWorkspace(String),
    Copy { seq: u64, text: String, what: String },
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
    /// Ask: a workspace to ask (by its place in the list); then the finished answer's actions and cited papers.
    Workspace(usize),
    CopyAnswer,
    OpenAnswer,
    Source(usize),
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
    /// The library's own sentence when it couldn't be listed (shown while nothing else is).
    pub library_error: Option<String>,
    /// Ask's workspaces once listed, and the one last asked (first in the list next time).
    pub workspaces: Option<Vec<Workspace>>,
    pub last_workspace: Option<String>,
    pub(crate) seq: u64,
    polling: Option<String>,
    /// Closed since it was last shown: an add finishing now is kept but not followed.
    hidden: bool,
}

impl Default for Panel {
    fn default() -> Self {
        Panel {
            mode: Mode::Find, query: String::new(), picked: 0, phase: Phase::Library, papers: vec![], reachable: true,
            library_error: None, workspaces: None, last_workspace: None, seq: 0, polling: None, hidden: false,
        }
    }
}

pub const UNREACHABLE: &str = "PaperLab isn't running. Open it, then try again.";

impl Panel {
    /// What Enter can act on now, in display order.
    pub fn rows(&self) -> Vec<Row> {
        match self.mode {
            Mode::Find => self.find_rows(),
            Mode::Cite => self.cite_rows(),
            Mode::Ask => self.ask_rows(),
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
            Event::Copied { seq, what, result } => self.copied(seq, what, result),
            Event::CloseNow(seq) => self.close_now(seq),
            Event::Novelty { seq, result } => self.novelty(seq, result),
            Event::Workspaces(result) => self.workspaces_arrived(result),
            Event::Heard { seq, result } => self.heard(seq, result),
            Event::Papers(result) => self.papers_arrived(result),
            Event::Looked { seq, result } => self.looked(seq, result),
            Event::AddDone { seq, result } => self.add_done(seq, result),
            Event::Status { id, result } => self.status(id, result),
        }
    }

    /// Opened again: a fresh field in the same mode, except that an Ask answer stays with its question (the user
    /// may have clicked away to paste it, or to wait for it).
    fn shown(&mut self) -> Vec<Effect> {
        let answer = matches!(self.phase, Phase::Answer(_)) && self.mode == Mode::Ask;
        let mut kept = Panel {
            mode: self.mode, papers: std::mem::take(&mut self.papers), reachable: self.reachable, seq: self.seq,
            workspaces: self.workspaces.take(), last_workspace: self.last_workspace.take(), ..Panel::default()
        };
        if answer {
            kept.phase = std::mem::replace(&mut self.phase, Phase::Library);
            kept.query = std::mem::take(&mut self.query);
        }
        *self = kept;
        [vec![Effect::FetchPapers], self.ask_entered()].concat()
    }

    /// Enter (or ⌘↵, `alt`): the mode's action on the picked row.
    fn submit(&mut self, alt: bool) -> Vec<Effect> {
        match self.mode {
            Mode::Find => self.find_submit(),
            Mode::Cite => self.cite_submit(if alt { Format::Bibtex } else { Format::Apa }),
            Mode::Ask => self.ask_submit(),
            Mode::Novelty => self.novelty_submit(),
        }
    }

    /// Another mode: what was typed stays (find a paper, then cite it); the last answer goes.
    fn set_mode(&mut self, mode: Mode) -> Vec<Effect> {
        if matches!(self.phase, Phase::Adding(_)) {
            return vec![]; // an add in flight keeps Find until it answers
        }
        (self.mode, self.phase, self.picked, self.polling) = (mode, Phase::Library, 0, None);
        self.ask_entered()
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
                (self.papers, self.reachable, self.library_error) = (papers, true, None);
                self.clamp();
            }
            Err(ApiError::Unreachable) => self.reachable = false,
            Err(ApiError::Said(sentence)) => (self.reachable, self.library_error) = (true, Some(sentence)),
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
