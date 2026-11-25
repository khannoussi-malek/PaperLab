//! Put papers in workspaces. Two ways in: PDFs dropped on the floating paper, once uploaded (the panel asks straight
//! away), and ⌘↵ on a paper in Find. The rows are a Done row, then the workspaces (the last one used first): Enter or
//! a click on a workspace picks or unpicks it, so several can be picked; typing narrows them; Enter on the Done row
//! puts every paper in every picked workspace and the panel closes. With none picked, the Done row (like Esc) leaves
//! them in the library only.

use super::ask::MAX_WORKSPACES;
use super::{Effect, Panel, Phase, Row, UNREACHABLE};
use crate::api::ApiError;

/// The papers being filed, the workspaces picked for them, and the put under way.
#[derive(Clone, Debug, PartialEq)]
pub struct Filing {
    pub paper_ids: Vec<String>,
    /// What's being filed, for sentences: “Its title”, or “these 3 papers”.
    pub what: String,
    /// The workspaces picked, by id, in the order picked.
    pub chosen: Vec<String>,
    /// The put under way (its seq).
    pub putting: Option<u64>,
    /// Why the last put didn't go through.
    pub error: Option<String>,
    /// What an upload came to when some PDFs didn't make it, said before the question.
    pub note: Option<String>,
}

impl Filing {
    pub fn new(paper_ids: Vec<String>, what: String, note: Option<String>) -> Self {
        Filing { paper_ids, what, chosen: vec![], putting: None, error: None, note }
    }
}

impl Panel {
    /// ⌘↵ in Find: the picked paper (a library one, or the one just added) is the one to file.
    pub(super) fn file_picked(&mut self) -> Vec<Effect> {
        let Some((paper_id, title)) = self.picked_paper() else { return vec![] };
        self.start_filing(Filing::new(vec![paper_id], format!("“{title}”"), None))
    }

    /// The question: the rows become the workspaces (fresh: one made in PaperLab a minute ago belongs in the list),
    /// the first workspace picked so Enter picks it.
    pub(super) fn start_filing(&mut self, filing: Filing) -> Vec<Effect> {
        (self.phase, self.query, self.picked, self.polling) = (Phase::Filing(filing), String::new(), 1, None);
        vec![Effect::FetchWorkspaces]
    }

    /// The Done row, then the workspaces whose name holds what's typed, the last one used first.
    pub(super) fn filing_rows(&self) -> Vec<Row> {
        let Some(all) = &self.workspaces else {
            return if self.reachable { vec![] } else { vec![Row::OpenPaperLab] };
        };
        let wanted = self.query.trim().to_lowercase();
        let workspaces = self.workspace_order_all().into_iter()
            .filter(|&i| all[i].name.to_lowercase().contains(&wanted))
            .take(MAX_WORKSPACES).map(Row::Workspace);
        std::iter::once(Row::FilingDone).chain(workspaces).collect()
    }

    /// Enter: on a workspace, pick or unpick it; on the Done row, put the papers in the picked ones (none picked:
    /// close, they stay in the library). Enter again while a put is under way waits for it.
    pub(super) fn file_submit(&mut self) -> Vec<Effect> {
        let Phase::Filing(filing) = &self.phase else { return vec![] };
        if filing.putting.is_some() {
            return vec![];
        }
        match self.filing_rows().into_iter().nth(self.picked) {
            Some(Row::FilingDone) if filing.chosen.is_empty() => vec![Effect::Close],
            Some(Row::FilingDone) => self.put(),
            Some(Row::Workspace(i)) => {
                let Some(id) = self.workspaces.as_ref().and_then(|all| all.get(i)).map(|w| w.id.clone()) else {
                    return vec![];
                };
                if let Phase::Filing(filing) = &mut self.phase {
                    match filing.chosen.iter().position(|c| *c == id) {
                        Some(at) => _ = filing.chosen.remove(at),
                        None => filing.chosen.push(id),
                    }
                    filing.error = None;
                }
                vec![]
            }
            Some(Row::OpenPaperLab) => vec![Effect::OpenPaperLab, Effect::Close],
            _ => vec![],
        }
    }

    fn put(&mut self) -> Vec<Effect> {
        self.seq += 1;
        let seq = self.seq;
        let Phase::Filing(filing) = &mut self.phase else { return vec![] };
        (filing.putting, filing.error) = (Some(seq), None);
        vec![Effect::PutInWorkspaces { seq, workspace_ids: filing.chosen.clone(), paper_ids: filing.paper_ids.clone() }]
    }

    /// Typing while filing narrows the workspaces (the Done row stays first).
    pub(super) fn filing_typed(&mut self, q: String) -> Vec<Effect> {
        (self.query, self.picked) = (q, 1);
        self.clamp();
        vec![]
    }

    /// The put's answer: done says so and closes a moment later (the first workspace picked comes first next time);
    /// otherwise the picks stay, with why, for Enter to try again.
    pub(super) fn put_done(&mut self, seq: u64, result: Result<(), ApiError>) -> Vec<Effect> {
        let Phase::Filing(filing) = &self.phase else { return vec![] };
        if filing.putting != Some(seq) {
            return vec![];
        }
        let filing = filing.clone();
        let error = match result {
            Ok(()) => {
                self.last_workspace = filing.chosen.first().cloned();
                self.phase = Phase::Filed(format!("Put {} in {}.", filing.what, self.chosen_names(&filing)));
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

    /// The picked workspaces' names, in a sentence: “Thesis”, “Thesis” and “RAG”, “A”, “B” and “C”.
    pub fn chosen_names(&self, filing: &Filing) -> String {
        let all = self.workspaces.as_deref().unwrap_or_default();
        let names: Vec<String> = filing.chosen.iter()
            .filter_map(|id| all.iter().find(|w| w.id == *id))
            .map(|w| format!("“{}”", w.name)).collect();
        match names.as_slice() {
            [] => String::new(),
            [one] => one.clone(),
            [rest @ .., last] => format!("{} and {last}", rest.join(", ")),
        }
    }
}
