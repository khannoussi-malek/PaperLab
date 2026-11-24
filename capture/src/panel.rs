//! The panel's behaviour as one state and one `step`: events in, effects out. No I/O here, so every path is tested
//! without a window or a server; `main.rs` performs the effects and feeds the answers back as events.

use crate::api::{Added, ApiError, Candidate, Found};
use crate::input::{Input, classify};
use crate::library::{Paper, matching};

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
    pub fn rows(&self) -> Vec<Row> {
        match &self.phase {
            Phase::Library if !self.reachable && self.papers.is_empty() => vec![Row::OpenPaperLab],
            Phase::Library => {
                let mut rows: Vec<Row> = matching(&self.papers, &self.query).into_iter().map(Row::Paper).collect();
                match classify(&self.query) {
                    Input::Text(t) => rows.push(Row::SearchOnline(t)),
                    input => rows.extend(input.lookup().map(|q| Row::SearchOnline(q.to_owned()))),
                }
                rows
            }
            Phase::Found(found) => (0..found.results.len()).map(Row::Candidate).collect(),
            Phase::Added(paper) => vec![Row::OpenAdded(paper.id.clone())],
            Phase::NoFreePdf { .. } => vec![Row::SaveWithoutPdf],
            Phase::Failed(_) if !self.reachable => vec![Row::OpenPaperLab],
            Phase::LookingUp(_) | Phase::Adding(_) | Phase::Failed(_) => vec![],
        }
    }

    pub fn step(&mut self, event: Event) -> Vec<Effect> {
        match event {
            Event::Shown => {
                *self = Panel { papers: std::mem::take(&mut self.papers), reachable: self.reachable, seq: self.seq, ..Panel::default() };
                vec![Effect::FetchPapers]
            }
            Event::Closed => {
                self.polling = None;
                self.hidden = true;
                vec![]
            }
            Event::Query(q) if matches!(self.phase, Phase::Adding(_)) => {
                self.query = q; // the add in flight keeps the panel: its answer must not be dropped
                vec![]
            }
            Event::Query(q) => {
                // A paste (more than one character at once) of a DOI, ID or link looks it up straight away; typed,
                // it waits for Enter on its "Search online" row so each keystroke doesn't ask every source.
                let pasted = q.len() > self.query.len() + 1;
                self.query = q;
                self.picked = 0;
                self.polling = None;
                match classify(&self.query).lookup() {
                    Some(query) if pasted => {
                        let query = query.to_owned();
                        self.look_up(query)
                    }
                    _ => {
                        self.phase = Phase::Library;
                        vec![]
                    }
                }
            }
            Event::Up | Event::Down => {
                let n = self.rows().len();
                if n > 0 {
                    self.picked = if event == Event::Down { (self.picked + 1) % n } else { (self.picked + n - 1) % n };
                }
                vec![]
            }
            Event::Submit => self.submit(),
            Event::Papers(Ok(papers)) => {
                self.papers = papers;
                self.reachable = true;
                self.clamp();
                vec![]
            }
            Event::Papers(Err(e)) => {
                self.reachable = e != ApiError::Unreachable;
                vec![]
            }
            Event::Looked { seq, result } => {
                if seq != self.seq || !matches!(self.phase, Phase::LookingUp(_)) {
                    return vec![]; // a later query or Esc made this answer stale
                }
                self.phase = match result {
                    Ok(found) => Phase::Found(found),
                    Err(e) => self.failed(e),
                };
                self.picked = 0;
                vec![]
            }
            Event::AddDone(result) => {
                let Phase::Adding(candidate) = &self.phase else { return vec![] };
                self.picked = 0; // the rows change: Enter acts on the first one
                match result {
                    Ok(Added::Queued(paper)) => {
                        let follow = !done(&paper) && !self.hidden;
                        let fx = if follow { vec![Effect::Poll(paper.id.clone())] } else { vec![] };
                        self.polling = (!fx.is_empty()).then(|| paper.id.clone());
                        self.phase = Phase::Added(paper);
                        fx
                    }
                    Ok(Added::AlreadyInLibrary(id)) => vec![Effect::Open(id), Effect::Close],
                    Ok(Added::NoFreePdf(message)) => {
                        self.phase = Phase::NoFreePdf { candidate: candidate.clone(), message };
                        vec![]
                    }
                    Err(e) => {
                        self.phase = self.failed(e);
                        vec![]
                    }
                }
            }
            Event::Status { id, result } => {
                if self.polling.as_deref() != Some(id.as_str()) {
                    return vec![];
                }
                match result {
                    Ok(paper) => {
                        let again = !done(&paper);
                        self.phase = Phase::Added(paper);
                        if again { vec![Effect::Poll(id)] } else { self.polling = None; vec![] }
                    }
                    Err(_) => {
                        self.polling = None; // keep the last status shown; the reader can open the paper anyway
                        vec![]
                    }
                }
            }
        }
    }

    fn submit(&mut self) -> Vec<Effect> {
        let Some(row) = self.rows().into_iter().nth(self.picked) else { return vec![] };
        match row {
            Row::Paper(i) => vec![Effect::Open(self.papers[i].id.clone()), Effect::Close],
            Row::SearchOnline(q) => self.look_up(q),
            Row::Candidate(i) => {
                let Phase::Found(found) = &self.phase else { return vec![] };
                let candidate = found.results[i].clone();
                match &candidate.paper_id {
                    Some(id) => vec![Effect::Open(id.clone()), Effect::Close],
                    None => {
                        self.phase = Phase::Adding(candidate.clone());
                        vec![Effect::Add { candidate, save_without_pdf: false }]
                    }
                }
            }
            Row::SaveWithoutPdf => {
                let Phase::NoFreePdf { candidate, .. } = &self.phase else { return vec![] };
                let candidate = candidate.clone();
                self.phase = Phase::Adding(candidate.clone());
                vec![Effect::Add { candidate, save_without_pdf: true }]
            }
            Row::OpenAdded(id) => vec![Effect::Open(id), Effect::Close],
            Row::OpenPaperLab => vec![Effect::OpenPaperLab, Effect::Close],
        }
    }

    fn look_up(&mut self, query: String) -> Vec<Effect> {
        self.seq += 1;
        self.picked = 0;
        self.phase = Phase::LookingUp(query.clone());
        vec![Effect::Lookup { seq: self.seq, query }]
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

fn done(paper: &Paper) -> bool {
    matches!(paper.status.as_str(), "ready" | "failed")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::library::paper;
    use serde_json::json;

    fn shown_with_library() -> Panel {
        let mut p = Panel::default();
        assert_eq!(p.step(Event::Shown), vec![Effect::FetchPapers]);
        p.step(Event::Papers(Ok(vec![
            paper("a", "Attention Is All You Need", &["Ashish Vaswani"], 2017, "2026-01"),
            paper("b", "Graph attention networks", &["Petar Velickovic"], 2018, "2026-02"),
        ])));
        p
    }

    fn candidate(title: &str, paper_id: Option<&str>) -> Candidate {
        Candidate { title: title.into(), authors: vec![], year: Some(2017), paper_id: paper_id.map(Into::into),
                    raw: json!({ "title": title }) }
    }

    fn typed(p: &mut Panel, text: &str) {
        for end in 1..=text.len() {
            p.step(Event::Query(text[..end].into()));
        }
    }

    #[test]
    fn type_pick_and_open_a_library_paper() {
        let mut p = shown_with_library();
        typed(&mut p, "attention");
        assert_eq!(p.rows(), vec![Row::Paper(0), Row::Paper(1), Row::SearchOnline("attention".into())]);
        p.step(Event::Down);
        assert_eq!(p.step(Event::Submit), vec![Effect::Open("b".into()), Effect::Close]);
    }

    #[test]
    fn up_wraps_and_an_empty_query_lists_newest() {
        let mut p = shown_with_library();
        assert_eq!(p.rows(), vec![Row::Paper(1), Row::Paper(0)]);
        p.step(Event::Up);
        assert_eq!(p.picked, 1);
    }

    #[test]
    fn a_pasted_doi_looks_up_at_once_but_a_typed_one_waits_for_enter() {
        let mut p = shown_with_library();
        let fx = p.step(Event::Query("https://doi.org/10.48550/arXiv.1706.03762".into()));
        assert_eq!(fx, vec![Effect::Lookup { seq: 1, query: "10.48550/arXiv.1706.03762".into() }]);
        assert_eq!(p.phase, Phase::LookingUp("10.48550/arXiv.1706.03762".into()));

        let mut p = shown_with_library();
        typed(&mut p, "10.1234/abc");
        assert_eq!(p.phase, Phase::Library);
        assert_eq!(p.rows(), vec![Row::SearchOnline("10.1234/abc".into())]);
        assert_eq!(p.step(Event::Submit), vec![Effect::Lookup { seq: 1, query: "10.1234/abc".into() }]);
    }

    #[test]
    fn a_stale_lookup_answer_changes_nothing() {
        let mut p = shown_with_library();
        p.step(Event::Query("10.1234/first".into()));
        p.step(Event::Query("10.1234/second-one".into()));
        let found = Found { results: vec![candidate("First", None)], notices: vec![] };
        p.step(Event::Looked { seq: 1, result: Ok(found) });
        assert_eq!(p.phase, Phase::LookingUp("10.1234/second-one".into()));
    }

    #[test]
    fn typing_while_adding_keeps_the_add_and_its_answer() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("New paper", None)], notices: vec![] }) });
        p.step(Event::Submit);
        assert_eq!(p.step(Event::Query("2401.12345x".into())), vec![]);
        let mut queued = paper("n", "New paper", &[], 2017, "2026");
        queued.status = "uploaded".into();
        assert_eq!(p.step(Event::AddDone(Ok(Added::Queued(queued)))), vec![Effect::Poll("n".into())]);
    }

    #[test]
    fn after_an_add_enter_acts_on_the_first_row_and_a_closed_panel_stops_following() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        let three = vec![candidate("A", None), candidate("B", None), candidate("C", None)];
        p.step(Event::Looked { seq: 1, result: Ok(Found { results: three, notices: vec![] }) });
        p.step(Event::Down);
        p.step(Event::Down);
        p.step(Event::Submit);
        p.step(Event::AddDone(Ok(Added::NoFreePdf("No free PDF.".into()))));
        assert_eq!(p.step(Event::Submit), vec![Effect::Add { candidate: candidate("C", None), save_without_pdf: true }]);

        p.step(Event::Closed);
        let mut queued = paper("c", "C", &[], 2017, "2026");
        queued.status = "uploaded".into();
        assert_eq!(p.step(Event::AddDone(Ok(Added::Queued(queued)))), vec![]); // kept, not polled while hidden
    }

    #[test]
    fn add_a_found_paper_and_follow_it_until_ready() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        let found = Found { results: vec![candidate("New paper", None)], notices: vec!["S2 is busy.".into()] };
        p.step(Event::Looked { seq: 1, result: Ok(found) });
        assert_eq!(p.rows(), vec![Row::Candidate(0)]);
        assert_eq!(p.step(Event::Submit), vec![Effect::Add { candidate: candidate("New paper", None), save_without_pdf: false }]);

        let mut queued = paper("n", "New paper", &[], 2017, "2026");
        queued.status = "uploaded".into();
        assert_eq!(p.step(Event::AddDone(Ok(Added::Queued(queued.clone())))), vec![Effect::Poll("n".into())]);
        queued.status = "embedding".into();
        assert_eq!(p.step(Event::Status { id: "n".into(), result: Ok(queued.clone()) }), vec![Effect::Poll("n".into())]);
        queued.status = "ready".into();
        assert_eq!(p.step(Event::Status { id: "n".into(), result: Ok(queued) }), vec![]);
        assert_eq!(p.rows(), vec![Row::OpenAdded("n".into())]);
        assert_eq!(p.step(Event::Submit), vec![Effect::Open("n".into()), Effect::Close]);
    }

    #[test]
    fn closing_stops_the_polling() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("New", None)], notices: vec![] }) });
        p.step(Event::Submit);
        let mut queued = paper("n", "New", &[], 2017, "2026");
        queued.status = "uploaded".into();
        p.step(Event::AddDone(Ok(Added::Queued(queued.clone()))));
        p.step(Event::Closed);
        assert_eq!(p.step(Event::Status { id: "n".into(), result: Ok(queued) }), vec![]);
    }

    #[test]
    fn a_candidate_already_held_opens_instead_of_adding() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("Held", Some("a"))], notices: vec![] }) });
        assert_eq!(p.step(Event::Submit), vec![Effect::Open("a".into()), Effect::Close]);
    }

    #[test]
    fn no_free_pdf_offers_save_without_pdf() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("Paywalled", None)], notices: vec![] }) });
        p.step(Event::Submit);
        p.step(Event::AddDone(Ok(Added::NoFreePdf("No free PDF was found for this paper.".into()))));
        assert_eq!(p.rows(), vec![Row::SaveWithoutPdf]);
        assert_eq!(p.step(Event::Submit), vec![Effect::Add { candidate: candidate("Paywalled", None), save_without_pdf: true }]);
    }

    #[test]
    fn offline_offers_to_open_paperlab_and_recovers() {
        let mut p = Panel::default();
        p.step(Event::Shown);
        p.step(Event::Papers(Err(ApiError::Unreachable)));
        assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
        assert_eq!(p.step(Event::Submit), vec![Effect::OpenPaperLab, Effect::Close]);
        p.step(Event::Papers(Ok(vec![paper("a", "A", &[], 2020, "2026")])));
        assert_eq!(p.rows(), vec![Row::Paper(0)]);
    }

    #[test]
    fn a_lookup_error_shows_paperlabs_sentence() {
        let mut p = shown_with_library();
        p.step(Event::Query("2401.12345".into()));
        p.step(Event::Looked { seq: 1, result: Err(ApiError::Said("No paper source that can look this up is on.".into())) });
        assert_eq!(p.phase, Phase::Failed("No paper source that can look this up is on.".into()));
    }
}
