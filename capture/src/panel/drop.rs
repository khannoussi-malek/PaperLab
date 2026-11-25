//! PDFs dropped on the floating paper: uploaded one after another, then the last one followed until it's ready, as an
//! add in Find is. Anything else dropped is turned away with what to do instead.

use std::path::PathBuf;

use super::{Effect, Panel, Phase, UNREACHABLE};
use crate::api::ApiError;
use crate::library::Paper;
use crate::mode::Mode;

pub const NOT_A_PDF: &str = "Only PDFs can be dropped on the paper. For a DOI, arXiv ID or link, paste it here instead.";

impl Panel {
    pub(super) fn dropped(&mut self, paths: Vec<PathBuf>) -> Vec<Effect> {
        if paths.is_empty() || matches!(self.phase, Phase::Adding(_) | Phase::Uploading { .. }) {
            return vec![]; // one upload or add at a time; the user can drop again once it's done
        }
        self.set_note_aside();
        self.seq += 1;
        (self.mode, self.picked, self.polling, self.upload_note) = (Mode::Find, 0, None, None);
        self.phase = Phase::Uploading { count: paths.len() };
        vec![Effect::Upload { seq: self.seq, paths }]
    }

    pub(super) fn drop_refused(&mut self) -> Vec<Effect> {
        if !matches!(self.phase, Phase::Adding(_) | Phase::Uploading { .. }) {
            self.set_note_aside();
            (self.mode, self.phase, self.polling) = (Mode::Find, Phase::Failed(NOT_A_PDF.into()), None);
        }
        vec![]
    }

    /// Every file's answer, in order: the last paper added is followed; failures are counted, the first one said.
    pub(super) fn uploaded(&mut self, seq: u64, results: Vec<Result<Paper, ApiError>>) -> Vec<Effect> {
        if seq != self.seq || !matches!(self.phase, Phase::Uploading { .. }) {
            return vec![];
        }
        let total = results.len();
        let (mut papers, mut errors) = (vec![], vec![]);
        for result in results {
            match result {
                Ok(paper) => papers.push(paper),
                Err(e) => errors.push(e),
            }
        }
        let first_error = (!errors.is_empty()).then(|| errors.swap_remove(0));
        let Some(paper) = papers.pop() else {
            self.phase = first_error.map_or(Phase::Library, |e| self.failed(e));
            return vec![];
        };
        self.upload_note = note(total, errors.len() + usize::from(first_error.is_some()), first_error);
        self.follow(paper)
    }
}

/// What a drop of several files came to; nothing to add for one.
fn note(total: usize, failed: usize, first_error: Option<ApiError>) -> Option<String> {
    match (total, first_error) {
        (1, _) => None,
        (_, None) => Some(format!("Added {total} PDFs; following the last one.")),
        (_, Some(e)) => {
            let why = match e {
                ApiError::Unreachable => UNREACHABLE.to_owned(),
                ApiError::Said(sentence) => sentence,
            };
            Some(format!("Added {} of {total} PDFs ({why}); following the last one.", total - failed))
        }
    }
}
