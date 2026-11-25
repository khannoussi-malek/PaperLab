//! Ask: a question to a workspace, answered from its papers as PaperLab writes it. The field is the question and the
//! rows are the workspaces, the last one asked first, so asking again is type and Enter. A finished answer offers to
//! copy it, to open it in PaperLab (the workspace's chat, where it is saved) and the papers it cites.

use super::{Effect, Panel, Phase, Row};
use crate::api::{ApiError, Said, Source, Workspace};

/// Rows of workspaces, and of cited papers, at most (the panel stays a glance; PaperLab shows the rest).
// ponytail: no workspace filter; the 7th workspace and on are reached through PaperLab until someone has that many.
pub(super) const MAX_WORKSPACES: usize = 6;
const MAX_SOURCES: usize = 3;

#[derive(Clone, Debug, PartialEq)]
pub struct Answer {
    pub seq: u64,
    pub workspace: Workspace,
    pub question: String,
    pub text: String,
    pub sources: Vec<Source>,
    pub state: Writing,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Writing {
    Under,
    Done,
    Failed(String),
}

/// A paper the answer cites, with every marker that points at it and the first page.
#[derive(Clone, Debug, PartialEq)]
pub struct Cited {
    pub paper_id: String,
    pub labels: Vec<String>,
    pub page: i32,
}

impl Answer {
    pub fn cited(&self) -> Vec<Cited> {
        let mut papers: Vec<Cited> = vec![];
        for s in &self.sources {
            match papers.iter_mut().find(|c| c.paper_id == s.paper_id) {
                Some(c) => c.labels.push(s.label.clone()),
                None => papers.push(Cited { paper_id: s.paper_id.clone(), labels: vec![s.label.clone()], page: s.page }),
            }
        }
        papers.truncate(MAX_SOURCES);
        papers
    }
}

impl Panel {
    pub(super) fn ask_rows(&self) -> Vec<Row> {
        match (&self.phase, &self.workspaces) {
            (Phase::Answer(a), _) => {
                let actions = if a.state == Writing::Done { vec![Row::CopyAnswer, Row::OpenAnswer] } else { vec![] };
                actions.into_iter().chain((0..a.cited().len()).map(Row::Source)).collect()
            }
            (Phase::Failed(_), _) | (_, None) if !self.reachable => vec![Row::OpenPaperLab],
            (_, Some(all)) if all.is_empty() => vec![Row::OpenPaperLab],
            (Phase::Library, Some(_)) => self.workspace_order().into_iter().map(Row::Workspace).collect(),
            _ => vec![],
        }
    }

    /// Workspace indices, the last one asked first.
    fn workspace_order(&self) -> Vec<usize> {
        self.workspace_order_all().into_iter().take(MAX_WORKSPACES).collect()
    }

    /// Every workspace's index, the last one used first.
    pub(super) fn workspace_order_all(&self) -> Vec<usize> {
        let Some(all) = &self.workspaces else { return vec![] };
        let last = all.iter().position(|w| Some(&w.id) == self.last_workspace.as_ref());
        last.into_iter().chain((0..all.len()).filter(|&i| Some(i) != last)).collect()
    }

    pub(super) fn ask_submit(&mut self) -> Vec<Effect> {
        let row = self.ask_rows().into_iter().nth(self.picked);
        match (row, &self.phase) {
            (Some(Row::Workspace(i)), _) => self.ask(i),
            (Some(Row::CopyAnswer), Phase::Answer(a)) => {
                let text = a.text.clone();
                self.aside = Some(a.clone()); // back on reopen, with Open in PaperLab and its papers
                self.seq += 1;
                self.phase = Phase::Copying;
                vec![Effect::Copy { seq: self.seq, text, what: "the answer".into() }]
            }
            (Some(Row::OpenAnswer), Phase::Answer(a)) => vec![Effect::OpenWorkspace { id: a.workspace.id.clone(), tab: "chat" }, Effect::Close],
            (Some(Row::Source(i)), Phase::Answer(a)) => vec![Effect::Open(a.cited()[i].paper_id.clone()), Effect::Close],
            (Some(Row::OpenPaperLab), _) => vec![Effect::OpenPaperLab, Effect::Close],
            _ => vec![],
        }
    }

    fn ask(&mut self, i: usize) -> Vec<Effect> {
        let (question, Some(all)) = (self.query.trim().to_owned(), &self.workspaces) else { return vec![] };
        if question.is_empty() {
            return vec![];
        }
        let workspace = all[i].clone();
        self.seq += 1;
        self.last_workspace = Some(workspace.id.clone());
        let ask = Effect::Ask { seq: self.seq, workspace_id: workspace.id.clone(), question: question.clone() };
        let answer = Answer { seq: self.seq, workspace, question, text: String::new(), sources: vec![], state: Writing::Under };
        self.phase = Phase::Answer(answer);
        self.picked = 0;
        vec![ask]
    }

    /// One step of the answer being written; one for an answer the user has since left is dropped.
    pub(super) fn heard(&mut self, seq: u64, result: Result<Said, ApiError>) -> Vec<Effect> {
        let on_screen = matches!(&self.phase, Phase::Answer(a) if a.seq == seq);
        let a = match (&mut self.phase, &mut self.aside) {
            (Phase::Answer(a), _) | (_, Some(a)) => a,
            _ => return vec![],
        };
        if a.seq != seq || a.state != Writing::Under {
            return vec![];
        }
        match result {
            Ok(Said::Sources(sources)) => a.sources = sources,
            Ok(Said::Token(text)) => a.text.push_str(&text),
            Ok(Said::Done) => a.state = Writing::Done,
            Ok(Said::Failed(sentence)) => a.state = Writing::Failed(sentence),
            Err(e) if on_screen => self.phase = self.failed(e),
            Err(ApiError::Unreachable) => a.state = Writing::Failed(super::UNREACHABLE.into()),
            Err(ApiError::Said(sentence)) => a.state = Writing::Failed(sentence),
        }
        if on_screen && matches!(&self.phase, Phase::Answer(a) if a.state == Writing::Done) {
            self.picked = 0;
        }
        vec![]
    }

    pub(super) fn workspaces_arrived(&mut self, result: Result<Vec<Workspace>, ApiError>) -> Vec<Effect> {
        match result {
            Ok(all) => (self.workspaces, self.reachable, self.ask_error) = (Some(all), true, None),
            Err(ApiError::Unreachable) => self.reachable = false,
            Err(ApiError::Said(sentence)) => self.ask_error = Some(sentence),
        }
        self.clamp();
        vec![]
    }

    /// The answer to keep when the panel reopens: the one on screen, or the one set aside.
    pub(super) fn answer_to_keep(&mut self) -> Option<Answer> {
        if !matches!(self.phase, Phase::Answer(_)) {
            return self.aside.take(); // other phases (an add in flight) stay where they are
        }
        match std::mem::replace(&mut self.phase, Phase::Library) {
            Phase::Answer(a) => Some(a),
            _ => None,
        }
    }
}
