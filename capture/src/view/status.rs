//! The one line under the field saying what's happening: looking up, adding, copied, searching, or what went wrong.

use crate::library::Paper;
use crate::panel::{Panel, Phase};

pub(super) fn line(p: &Panel) -> Option<String> {
    match &p.phase {
        Phase::Library => None,
        Phase::LookingUp(q) => Some(format!("Looking up {q}…")),
        Phase::Found(f) if f.results.is_empty() => Some(join("Nothing found.", &f.notices)),
        Phase::Found(f) => (!f.notices.is_empty()).then(|| f.notices.join(" ")),
        Phase::Adding(c) => Some(format!("Adding “{}”…", c.title)),
        Phase::Added(paper) => Some(progress(paper)),
        Phase::NoFreePdf { message, .. } => Some(message.clone()),
        Phase::Failed(sentence) | Phase::Copied(sentence) => Some(sentence.clone()),
        Phase::Searching => Some("Looking through your library for papers close to it…".into()),
        Phase::Close(c) if c.papers.is_empty() => Some(join("Nothing in your library is close.", std::slice::from_ref(&c.note))),
        Phase::Close(c) => (!c.note.is_empty()).then(|| c.note.clone()),
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
