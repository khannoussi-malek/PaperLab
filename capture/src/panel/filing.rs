//! Put a paper in a workspace from Find: ⌘↵ on a library paper (or on the one just added) turns the rows into the
//! workspaces, the last one used first; typing narrows them, Enter puts the paper there and the panel closes.

use super::ask::MAX_WORKSPACES;
use super::{Effect, Panel, Phase, Row, UNREACHABLE};
use crate::api::ApiError;

/// The paper being put in a workspace, and the put under way (its seq and the workspace's name).
#[derive(Clone, Debug, PartialEq)]
pub struct Filing {
    pub paper_id: String,
    pub title: String,
    pub putting: Option<(u64, String)>,
    /// Why the last put didn't go through.
    pub error: Option<String>,
}

impl Panel {
    /// ⌘↵ in Find: the picked paper (a library one, or the one just added) is the one to file.
    pub(super) fn file_picked(&mut self) -> Vec<Effect> {
        let Some((paper_id, title)) = self.picked_paper() else { return vec![] };
        let filing = Filing { paper_id, title, putting: None, error: None };
        (self.phase, self.query, self.picked, self.polling) = (Phase::Filing(filing), String::new(), 0, None);
        vec![Effect::FetchWorkspaces] // fresh: one made in PaperLab a minute ago belongs in the list
    }

    /// The workspaces whose name holds what's typed, the last one used first.
    pub(super) fn filing_rows(&self) -> Vec<Row> {
        let Some(all) = &self.workspaces else {
            return if self.reachable { vec![] } else { vec![Row::OpenPaperLab] };
        };
        if all.is_empty() {
            return vec![Row::OpenPaperLab];
        }
        let wanted = self.query.trim().to_lowercase();
        self.workspace_order_all().into_iter()
            .filter(|&i| all[i].name.to_lowercase().contains(&wanted))
            .take(MAX_WORKSPACES).map(Row::Workspace).collect()
    }

    /// Enter while filing: put the paper in the picked workspace (once; Enter again waits for the answer).
    pub(super) fn file_submit(&mut self) -> Vec<Effect> {
        let Phase::Filing(filing) = &self.phase else { return vec![] };
        if filing.putting.is_some() {
            return vec![];
        }
        match self.filing_rows().into_iter().nth(self.picked) {
            Some(Row::Workspace(i)) => {
                let Some(workspace) = self.workspaces.as_ref().and_then(|all| all.get(i)).cloned() else { return vec![] };
                self.seq += 1;
                let effect =
                    Effect::PutInWorkspace { seq: self.seq, workspace_id: workspace.id, paper_id: filing.paper_id.clone() };
                let putting = Some((self.seq, workspace.name));
                self.phase = Phase::Filing(Filing { putting, error: None, ..filing.clone() });
                vec![effect]
            }
            Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
            _ => vec![],
        }
    }

    /// Typing while filing narrows the workspaces.
    pub(super) fn filing_typed(&mut self, q: String) -> Vec<Effect> {
        (self.query, self.picked) = (q, 0);
        vec![]
    }

    /// The put's answer: done says so and closes a moment later (that workspace comes first next time); otherwise
    /// the list stays, with why.
    pub(super) fn put_done(&mut self, seq: u64, workspace_id: String, result: Result<(), ApiError>) -> Vec<Effect> {
        let Phase::Filing(filing) = &self.phase else { return vec![] };
        let Some((sent, name)) = &filing.putting else { return vec![] };
        if *sent != seq {
            return vec![];
        }
        let (title, name, filing) = (filing.title.clone(), name.clone(), filing.clone());
        let error = match result {
            Ok(()) => {
                self.last_workspace = Some(workspace_id);
                self.phase = Phase::Filed(format!("Put “{title}” in “{name}”."));
                return vec![Effect::CloseSoon(seq)];
            }
            Err(ApiError::Unreachable) => {
                self.reachable = false;
                UNREACHABLE.to_owned()
            }
            Err(ApiError::Said(sentence)) => sentence,
        };
        self.phase = Phase::Filing(Filing { putting: None, error: Some(error), ..filing });
        vec![]
    }
}
