//! The one line under the field saying what's happening: looking up, adding, copied, searching, or what went wrong.

use crate::library::Paper;
use crate::mode::Mode;
use crate::panel::{Answer, Filing, Panel, Phase, Writing};

pub(super) fn line(p: &Panel) -> Option<String> {
    match &p.phase {
        Phase::Library if p.mode == Mode::Ask => p.ask_error.clone().or_else(|| ask_hint(p)),
        Phase::Library if p.mode == Mode::Inbox => p.inbox_error.clone().or_else(|| inbox_hint(p)),
        Phase::Library => p.library_error.clone(),
        Phase::Answer(a) => Some(answering(a)),
        Phase::Copying => Some("Copying…".into()),
        Phase::LookingUp(q) => Some(format!("Looking up {q}…")),
        Phase::Found(f) if f.results.is_empty() => Some(join("Nothing found.", &f.notices)),
        Phase::Found(f) => (!f.notices.is_empty()).then(|| f.notices.join(" ")),
        Phase::Adding(c) => Some(format!("Adding “{}”…", c.title)),
        Phase::Uploading { count: 1 } => Some("Uploading the PDF…".into()),
        Phase::Uploading { count } => Some(format!("Uploading {count} PDFs…")),
        Phase::Added(paper) => Some(match &p.upload_note {
            Some(note) => format!("{note} {}", progress(paper)),
            None => progress(paper),
        }),
        Phase::NoFreePdf { message, .. } => Some(message.clone()),
        Phase::Failed(sentence) | Phase::Copied(sentence) => Some(sentence.clone()),
        Phase::Searching => Some("Looking through your library for papers close to it…".into()),
        Phase::Close(c) if c.papers.is_empty() => Some(join("Nothing in your library is close.", std::slice::from_ref(&c.note))),
        Phase::Close(c) => (!c.note.is_empty()).then(|| c.note.clone()),
        Phase::Note(d) => Some(d.error.clone().unwrap_or_else(|| format!("A note on “{}”: ↵ saves it to the paper.", d.title))),
        Phase::SavingNote(d) => Some(format!("Saving your note on “{}”…", d.title)),
        Phase::NoteSaved(sentence) | Phase::Filed(sentence) => Some(sentence.clone()),
        Phase::Filing(f) => Some(filing(p, f)),
    }
}

/// Ask before a question: what the rows are, or why there are none.
fn ask_hint(p: &Panel) -> Option<String> {
    match &p.workspaces {
        None if p.reachable => Some("Listing your workspaces…".into()),
        Some(all) if all.is_empty() => Some("Ask answers from a workspace's papers: make a workspace in PaperLab first.".into()),
        Some(_) if p.query.trim().is_empty() => Some("Type a question; ↵ asks the workspace picked below.".into()),
        _ => None,
    }
}

fn inbox_hint(p: &Panel) -> Option<String> {
    match &p.inbox {
        None if p.reachable => Some("Looking for what's new…".into()),
        Some(inbox) if inbox.count() == 0 => {
            Some("Nothing new. Free PDFs the weekly re-check finds and new saved-search results show up here.".into())
        }
        _ => None,
    }
}

fn answering(a: &Answer) -> String {
    let name = &a.workspace.name;
    match &a.state {
        Writing::Under if a.text.is_empty() => format!("Reading the papers in “{name}”…"),
        Writing::Under => format!("Writing the answer from “{name}”…"),
        Writing::Done => match a.cited().len() {
            0 => format!("Answered from “{name}”."),
            n => format!("Answered from “{name}”, citing {n} paper{}.", if n == 1 { "" } else { "s" }),
        },
        Writing::Failed(sentence) => sentence.clone(),
    }
}

/// The added paper's ingest status in words.
fn progress(paper: &Paper) -> String {
    match paper.status.as_str() {
        "ready" => "Ready.".into(),
        "failed" => format!("Couldn't read it: {}", paper.status_error.as_deref().unwrap_or("no reason given.")),
        "uploaded" => "Added, waiting its turn…".into(),
        "extracting" => "Reading the PDF…".into(),
        "chunking" | "embedding" => "Indexing for search…".into(),
        "enriching" => "Filling in its details…".into(),
        other => format!("{other}…"),
    }
}

fn join(head: &str, notices: &[String]) -> String {
    std::iter::once(head).chain(notices.iter().map(String::as_str).filter(|n| !n.is_empty())).collect::<Vec<_>>().join(" ")
}

/// Filing: what's under way, what went wrong, or what to do.
fn filing(p: &Panel, f: &Filing) -> String {
    match (&f.putting, &f.error, &p.workspaces) {
        (Some((_, name)), _, _) => format!("Putting it in “{name}”…"),
        (None, Some(error), _) => error.clone(),
        (None, None, None) => p.ask_error.clone().unwrap_or_else(|| "Listing your workspaces…".into()),
        (None, None, Some(all)) if all.is_empty() => "Make a workspace in PaperLab first.".into(),
        (None, None, Some(_)) if p.rows().is_empty() => format!("No workspace’s name holds “{}”.", p.query.trim()),
        _ => format!("Which workspace for “{}”?", f.title),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::{ApiError, Workspace};
    use crate::panel::Event;

    fn filing() -> Panel {
        let mut p = Panel::default();
        p.step(Event::Papers(Ok(vec![crate::library::paper("a", "Attention", &[], 2017, "2026-01")])));
        p.step(Event::SubmitAlt);
        assert!(matches!(p.phase, Phase::Filing(_)));
        p
    }

    #[test]
    fn filing_says_why_a_list_is_missing_or_empty() {
        let mut p = filing();
        assert_eq!(line(&p).as_deref(), Some("Listing your workspaces…"));
        p.step(Event::Workspaces(Err(ApiError::Said("The database is busy.".into()))));
        assert_eq!(line(&p).as_deref(), Some("The database is busy."), "not “Listing…” forever");
        p.step(Event::Workspaces(Ok(vec![Workspace { id: "w".into(), name: "Thesis".into(), paper_count: 1 }])));
        p.step(Event::Query("zzz".into()));
        assert_eq!(line(&p).as_deref(), Some("No workspace’s name holds “zzz”."));
    }
}
