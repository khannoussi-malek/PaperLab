//! The panel's modes: one PaperLab function each, in the order the mode bar shows them.

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Mode {
    /// Filter the library and open a paper; look a DOI, arXiv ID or link up and add it.
    #[default]
    Find,
    /// Find a library paper and copy its reference.
    Cite,
    /// Ask a workspace a question; the answer streams in, with the papers it cites.
    Ask,
    /// Find a paper, then write a note on it.
    Note,
    /// Paste an idea: the closest papers in the library.
    Novelty,
    /// What's new: free PDFs found for saved papers, saved searches with new results.
    Inbox,
}

/// The mode bar, left to right; Tab moves along it and ⌘1, ⌘2… jump to a place in it.
pub const MODES: [Mode; 6] = [Mode::Find, Mode::Cite, Mode::Ask, Mode::Note, Mode::Novelty, Mode::Inbox];

impl Mode {
    pub fn label(self) -> &'static str {
        match self {
            Mode::Find => "Find",
            Mode::Cite => "Cite",
            Mode::Ask => "Ask",
            Mode::Note => "Note",
            Mode::Novelty => "Done before?",
            Mode::Inbox => "Inbox",
        }
    }

    /// What the field asks for in this mode.
    pub fn placeholder(self) -> &'static str {
        match self {
            Mode::Find => "Find a paper, or paste a DOI, arXiv ID or link",
            Mode::Cite => "Find the paper to cite: ↵ copies APA, ⌘↵ BibTeX",
            Mode::Ask => "Ask a workspace a question, then ↵",
            Mode::Note => "Find the paper to write on, then ↵",
            Mode::Novelty => "Paste an idea or an abstract, then ↵: has it been done?",
            Mode::Inbox => "What's new since you last looked; ↵ opens it",
        }
    }

    /// The next mode along the bar (or the previous), wrapping round.
    pub fn step(self, forward: bool) -> Mode {
        let at = MODES.iter().position(|&m| m == self).unwrap_or(0);
        let n = MODES.len();
        MODES[if forward { (at + 1) % n } else { (at + n - 1) % n }]
    }

    /// The mode at a 1-based place in the bar (⌘1 is the first).
    pub fn nth(place: usize) -> Option<Mode> {
        place.checked_sub(1).and_then(|i| MODES.get(i).copied())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tab_walks_the_bar_both_ways_and_wraps() {
        let last = *MODES.last().unwrap();
        assert_eq!(Mode::Find.step(true), MODES[1]);
        assert_eq!(last.step(true), Mode::Find);
        assert_eq!(Mode::Find.step(false), last);
    }

    #[test]
    fn command_digits_jump_to_a_place_in_the_bar() {
        assert_eq!(Mode::nth(1), Some(Mode::Find));
        assert_eq!(Mode::nth(MODES.len()), MODES.last().copied());
        assert_eq!((Mode::nth(0), Mode::nth(MODES.len() + 1)), (None, None));
    }

    #[test]
    fn every_mode_has_its_own_label_and_prompt() {
        let labels: std::collections::HashSet<_> = MODES.iter().map(|m| m.label()).collect();
        assert_eq!(labels.len(), MODES.len());
        assert!(MODES.iter().all(|m| !m.placeholder().is_empty()));
    }
}
