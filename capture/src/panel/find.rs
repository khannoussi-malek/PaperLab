//! Find: filter the library as you type and open a paper; look a DOI, arXiv ID or link up and add it, then follow it
//! until it's ready.

use super::{Effect, Panel, Phase, Row};
use crate::api::{Added, ApiError, Candidate, Found};
use crate::input::{Input, classify};
use crate::library::{Paper, matching};

impl Panel {
    pub(super) fn find_rows(&self) -> Vec<Row> {
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
            Phase::LookingUp(_) | Phase::Adding(_) | Phase::Uploading { .. } | Phase::Failed(_) => vec![],
            // other modes' phases
            Phase::Copying | Phase::Copied(_) | Phase::Searching | Phase::Close(_) | Phase::Answer(_) => vec![],
            Phase::Note(_) | Phase::SavingNote(_) | Phase::NoteSaved(_) => vec![],
            Phase::Filing(_) => self.filing_rows(),
            Phase::Filed(_) => vec![],
        }
    }

    pub(super) fn find_query(&mut self, q: String) -> Vec<Effect> {
        if self.in_flight() {
            self.query = q; // the add in flight keeps the panel: its answer must not be dropped
            return vec![];
        }
        // A paste (more than one character at once) of a DOI, ID or link looks it up straight away; typed,
        // it waits for Enter on its "Search online" row so each keystroke doesn't ask every source.
        let pasted = q.len() > self.query.len() + 1;
        self.query = q;
        (self.picked, self.polling, self.upload_note) = (0, None, None);
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

    pub(super) fn looked(&mut self, seq: u64, result: Result<Found, ApiError>) -> Vec<Effect> {
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

    fn add(&mut self, candidate: Candidate, save_without_pdf: bool) -> Vec<Effect> {
        self.seq += 1;
        self.phase = Phase::Adding(candidate.clone());
        vec![Effect::Add { seq: self.seq, candidate, save_without_pdf }]
    }

    pub(super) fn add_done(&mut self, seq: u64, result: Result<Added, ApiError>) -> Vec<Effect> {
        let Phase::Adding(candidate) = &self.phase else { return vec![] };
        if seq != self.seq {
            return vec![]; // an earlier add, answering while a newer one is under way
        }
        let candidate = candidate.clone();
        self.picked = 0; // the rows change: Enter acts on the first one
        match result {
            Ok(Added::Queued(paper)) => self.follow(paper),
            Ok(Added::AlreadyInLibrary(id)) => vec![Effect::Open(id), Effect::Close],
            Ok(Added::NoFreePdf(message)) => {
                self.phase = Phase::NoFreePdf { candidate, message };
                vec![]
            }
            Err(e) => {
                self.phase = self.failed(e);
                vec![]
            }
        }
    }

    /// A paper just added: shown, and followed until it's ready while the panel is open.
    pub(super) fn follow(&mut self, paper: Paper) -> Vec<Effect> {
        let follow = !done(&paper) && !self.hidden;
        self.polling = follow.then(|| paper.id.clone());
        let fx = if follow { vec![Effect::Poll(paper.id.clone())] } else { vec![] };
        self.phase = Phase::Added(paper);
        fx
    }

    pub(super) fn status(&mut self, id: String, result: Result<Paper, ApiError>) -> Vec<Effect> {
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

    pub(super) fn find_submit(&mut self) -> Vec<Effect> {
        let Some(row) = self.rows().into_iter().nth(self.picked) else { return vec![] };
        match row {
            Row::Paper(i) => vec![Effect::Open(self.papers[i].id.clone()), Effect::Close],
            Row::SearchOnline(q) => self.look_up(q),
            Row::Candidate(i) => {
                let Phase::Found(found) = &self.phase else { return vec![] };
                let candidate = found.results[i].clone();
                match &candidate.paper_id {
                    Some(id) => vec![Effect::Open(id.clone()), Effect::Close],
                    None => self.add(candidate, false),
                }
            }
            Row::SaveWithoutPdf => {
                let Phase::NoFreePdf { candidate, .. } = &self.phase else { return vec![] };
                let candidate = candidate.clone();
                self.add(candidate, true)
            }
            Row::OpenAdded(id) => vec![Effect::Open(id), Effect::Close],
            Row::OpenPaperLab => vec![Effect::OpenPaperLab, Effect::Close],
            Row::Close(_) | Row::Workspace(_) | Row::CopyAnswer | Row::OpenAnswer | Row::Source(_) | Row::FoundPdf(_) | Row::NewHits(_) => vec![], // other modes' rows
        }
    }

    /// The paper picked in Find, as (id, title): a library paper, or the one just added. What ⌘↵ files and ⌘L
    /// looks like.
    pub(super) fn picked_paper(&self) -> Option<(String, String)> {
        match (self.rows().into_iter().nth(self.picked), &self.phase) {
            (Some(Row::Paper(i)), _) => Some((self.papers[i].id.clone(), self.papers[i].title.clone())),
            (Some(Row::OpenAdded(_)), Phase::Added(added)) => Some((added.id.clone(), added.title.clone())),
            _ => None,
        }
    }

    /// ⌘L: papers like the picked one, as a lookup's results: Enter adds one.
    pub(super) fn similar(&mut self) -> Vec<Effect> {
        let Some((paper_id, title)) = self.picked_paper() else { return vec![] };
        self.seq += 1;
        (self.picked, self.polling) = (0, None);
        self.phase = Phase::LookingUp(format!("papers like “{title}”"));
        vec![Effect::Similar { seq: self.seq, paper_id }]
    }

    fn look_up(&mut self, query: String) -> Vec<Effect> {
        self.seq += 1;
        self.picked = 0;
        self.phase = Phase::LookingUp(query.clone());
        vec![Effect::Lookup { seq: self.seq, query }]
    }
}

fn done(paper: &Paper) -> bool {
    matches!(paper.status.as_str(), "ready" | "failed")
}
