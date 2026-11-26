//! The panel's behaviour as one state and one `step`: events in, effects out. No I/O here, so every path is tested
//! without a window or a server; `main.rs` performs the effects and feeds the answers back as events. Each mode's own
//! rules live in its module beside this one; this one holds the state and routes events to them.

mod ask;
mod cite;
mod drop;
mod filing;
mod find;
mod inbox;
mod note;
mod novelty;
#[cfg(test)]
mod tests;

pub use ask::{Answer, Writing};
pub use filing::Filing;
pub use note::Draft;
use note::Aside;

use std::path::PathBuf;

use crate::api::{Added, ApiError, Candidate, Closeness, Format, Found, Inbox, Said, Workspace};
use crate::library::Paper;
use crate::mode::Mode;

#[derive(Clone, Debug, PartialEq)]
pub enum Phase {
    /// Local results for the query (newest papers when it's empty).
    Library,
    LookingUp(String),
    Found(Found),
    Adding(Candidate),
    /// PDFs dropped on the floating paper, on their way up.
    Uploading { count: usize },
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
    /// Note: one being written on a paper (the field holds it), being saved, saved (the sentence saying where).
    Note(Draft),
    SavingNote(Draft),
    NoteSaved(String),
    /// Find, ⌘↵ on a paper: picking the workspace to put it in; then the sentence saying where it went.
    Filing(Filing),
    Filed(String),
    /// A file is being dragged over the floating paper: the panel waits under the pointer for the drop.
    DropHere,
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
    /// ⌘L in Find: papers like the picked one.
    Similar,
    /// Something reached the clipboard (`what`: "the APA reference of “…”"), or didn't.
    Copied { seq: u64, what: String, result: Result<(), ApiError> },
    /// A moment after a copy: close if "Copied …" is still what the panel shows.
    CloseNow(u64),
    Novelty { seq: u64, result: Result<Closeness, ApiError> },
    Workspaces(Result<Vec<Workspace>, ApiError>),
    /// One step of an answer as PaperLab writes it; an error before the first.
    Heard { seq: u64, result: Result<Said, ApiError> },
    /// Files dropped on the floating paper: PDFs, or something else.
    Dropped(Vec<PathBuf>),
    DropRefused,
    Uploaded { seq: u64, results: Vec<Result<Paper, ApiError>> },
    Inbox(Result<Inbox, ApiError>),
    NoteSaved { seq: u64, result: Result<(), ApiError> },
    Put { seq: u64, result: Result<(), ApiError> },
    /// A click on a row: pick it and act on it, as Enter would.
    Click(usize),
    /// A file is being dragged over the floating paper (the panel opens for the drop), and that drag ended.
    DropOffered,
    DragEnded,
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
    /// A workspace in PaperLab at one of its tabs: "chat" (where an Ask answer is saved), "search".
    OpenWorkspace { id: String, tab: &'static str },
    FetchInbox,
    /// The owner opened a free PDF the re-check found: it leaves the Inbox.
    FoundSeen(String),
    Copy { seq: u64, text: String, what: String },
    /// Save a note on a whole paper.
    SaveNote { seq: u64, paper_id: String, body: String },
    /// Put every paper in every workspace.
    PutInWorkspaces { seq: u64, workspace_ids: Vec<String>, paper_ids: Vec<String> },
    /// Papers like a library one; the answer comes back as a lookup's (`Event::Looked`).
    Similar { seq: u64, paper_id: String },
    Upload { seq: u64, paths: Vec<PathBuf> },
    /// A paper from a link to its PDF; its answer comes back as an upload's (`Event::Uploaded`).
    AddLink { seq: u64, link: String },
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
    /// Inbox: a free PDF found, a saved search with new results.
    FoundPdf(usize),
    NewHits(usize),
    /// Filing: put the papers in the workspaces picked (or, none picked, leave them in the library).
    FilingDone,
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
    /// Ask's own sentence when the workspaces couldn't be listed.
    pub ask_error: Option<String>,
    /// An Ask answer off screen: copied from (the copy replaced it), or set aside when the panel reopened in another
    /// mode. It keeps filling in as it streams, and reopening in Ask brings it back.
    aside: Option<Answer>,
    /// A note off screen, waiting for Note (see note.rs).
    note_aside: Option<Aside>,
    /// What's new, once listed (the floating paper's badge counts it).
    pub inbox: Option<Inbox>,
    /// PaperLab's sentence when the Inbox couldn't be listed.
    pub inbox_error: Option<String>,
    pub(crate) seq: u64,
    polling: Option<String>,
    /// Closed since it was last shown: an add finishing now is kept but not followed.
    hidden: bool,
}

impl Default for Panel {
    fn default() -> Self {
        Panel {
            mode: Mode::Find, query: String::new(), picked: 0, phase: Phase::Library, papers: vec![], reachable: true,
            library_error: None, workspaces: None, last_workspace: None, ask_error: None, aside: None, note_aside: None, inbox: None, inbox_error: None, seq: 0, polling: None, hidden: false,
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
            Mode::Inbox => self.inbox_rows(),
            Mode::Novelty => self.novelty_rows(),
            Mode::Note => self.note_rows(),
        }
    }

    pub fn step(&mut self, event: Event) -> Vec<Effect> {
        match event {
            Event::Shown => self.shown(),
            Event::Closed => self.closed(),
            Event::Query(q) if self.mode == Mode::Find && matches!(self.phase, Phase::Filing(_)) => self.filing_typed(q),
            Event::Query(q) if self.mode == Mode::Find => self.find_query(q),
            Event::Query(q) if self.mode == Mode::Note => self.note_typed(q),
            Event::Query(q) => self.typed(q),
            Event::Up => self.pick_by(-1),
            Event::Down => self.pick_by(1),
            Event::Submit => self.submit(false),
            Event::SubmitAlt => self.submit(true),
            Event::Similar if self.mode == Mode::Find && !self.in_flight() => self.similar(),
            Event::Similar => vec![],
            Event::Mode(mode) => self.set_mode(mode),
            Event::NextMode { forward } => self.set_mode(self.mode.step(forward)),
            Event::Copied { seq, what, result } => self.copied(seq, what, result),
            Event::CloseNow(seq) => self.close_now(seq),
            Event::Novelty { seq, result } => self.novelty(seq, result),
            Event::Workspaces(result) => self.workspaces_arrived(result),
            Event::Heard { seq, result } => self.heard(seq, result),
            Event::Dropped(paths) => self.dropped(paths),
            Event::DropRefused => self.drop_refused(),
            Event::DropOffered => self.drop_offered(),
            Event::DragEnded => self.drag_ended(),
            Event::Uploaded { seq, results } => self.uploaded(seq, results),
            Event::Inbox(result) => self.inbox_arrived(result),
            Event::NoteSaved { seq, result } => self.note_saved(seq, result),
            Event::Put { seq, result } => self.put_done(seq, result),
            Event::Click(row) if row < self.rows().len() => {
                self.picked = row;
                self.submit(false)
            }
            Event::Click(_) => vec![],
            Event::Papers(result) => self.papers_arrived(result),
            Event::Looked { seq, result } => self.looked(seq, result),
            Event::AddDone { seq, result } => self.add_done(seq, result),
            Event::Status { id, result } => self.status(id, result),
        }
    }

    /// Opened again: a fresh field in the same mode, except that an Ask answer comes back with its question (the user
    /// may have clicked away to paste it, or to wait for it). Opened in another mode, the answer waits aside for Ask.
    fn shown(&mut self) -> Vec<Effect> {
        // An add or upload still under way stays on screen, so its answer is shown and followed; it keeps Find,
        // whatever mode the panel was opened in. A note waits aside unless the panel opened in Note.
        let in_flight = self.in_flight();
        if self.mode != Mode::Note {
            self.set_note_aside();
        }
        let answer = self.answer_to_keep();
        let mut kept = Panel {
            mode: if in_flight { Mode::Find } else { self.mode },
            papers: std::mem::take(&mut self.papers), reachable: self.reachable, seq: self.seq,
            workspaces: self.workspaces.take(), last_workspace: self.last_workspace.take(), inbox: self.inbox.take(),
            note_aside: self.note_aside.take(),
            ..Panel::default()
        };
        match answer {
            Some(a) if kept.mode == Mode::Ask => {
                kept.query = a.question.clone();
                kept.phase = Phase::Answer(a);
            }
            aside => kept.aside = aside,
        }
        if in_flight || matches!(self.phase, Phase::Note(_) | Phase::SavingNote(_)) {
            kept.query = std::mem::take(&mut self.query);
            kept.phase = std::mem::replace(&mut self.phase, Phase::Library);
        }
        *self = kept;
        self.bring_note_back();
        [vec![Effect::FetchPapers], self.entered()].concat()
    }

    /// Enter (or ⌘↵, `alt`): the mode's action on the picked row.
    fn submit(&mut self, alt: bool) -> Vec<Effect> {
        match self.mode {
            Mode::Find if matches!(self.phase, Phase::Filing(_)) => self.file_submit(),
            Mode::Find if alt => self.file_picked(),
            Mode::Find => self.find_submit(),
            Mode::Cite => self.cite_submit(if alt { Format::Bibtex } else { Format::Apa }),
            Mode::Ask => self.ask_submit(),
            Mode::Inbox => self.inbox_submit(),
            Mode::Novelty => self.novelty_submit(),
            Mode::Note => self.note_submit(),
        }
    }

    /// Another mode: what was typed stays (find a paper, then cite it); the last answer goes.
    fn set_mode(&mut self, mode: Mode) -> Vec<Effect> {
        if self.in_flight() {
            return vec![]; // an add, upload or put in flight keeps Find until it answers
        }
        self.set_note_aside();
        (self.mode, self.phase, self.picked, self.polling, self.aside) = (mode, Phase::Library, 0, None, None);
        self.bring_note_back();
        self.entered()
    }

    /// Entering a mode (or opening the panel in it): what it lists, fresh.
    fn entered(&self) -> Vec<Effect> {
        match self.mode {
            Mode::Ask => vec![Effect::FetchWorkspaces],
            Mode::Inbox => vec![Effect::FetchInbox],
            Mode::Find | Mode::Cite | Mode::Novelty | Mode::Note => vec![],
        }
    }

    /// Typing in a mode other than Find: the text is the query; an earlier answer, or one still coming, no longer
    /// matches it.
    fn typed(&mut self, q: String) -> Vec<Effect> {
        (self.query, self.picked, self.phase, self.aside) = (q, 0, Phase::Library, None);
        vec![]
    }

    /// An add, an upload or a put under way: its answer must find the panel where it left it, so Find stays.
    fn in_flight(&self) -> bool {
        match &self.phase {
            Phase::Adding(_) | Phase::Uploading { .. } => true,
            Phase::Filing(filing) => filing.putting.is_some(),
            _ => false,
        }
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
