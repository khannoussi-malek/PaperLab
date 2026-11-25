//! The one line under the field saying what's happening: looking up, adding, copied, searching, or what went wrong.

use crate::library::Paper;
use crate::mode::Mode;
use crate::panel::{Answer, Panel, Phase, Writing};

pub(super) fn line(p: &Panel) -> Option<String> {
    match &p.phase {
        Phase::Library if p.mode == Mode::Ask => p.ask_error.clone().or_else(|| ask_hint(p)),
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
