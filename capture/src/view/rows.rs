//! The rows Enter acts on: a title, a detail line and, on the right, what Enter does with it.

use rune::tok::type_;
use rune::{Color, El, col, row, text};

use super::{Ink, logo_blue};
use crate::api::Close;
use crate::library::byline;
use crate::mode::Mode;
use crate::panel::{Panel, Phase, Row, UNREACHABLE};

/// The rows, the picked one in the logo's blue; None when there are none.
pub(super) fn list(p: &Panel, ink: &Ink) -> Option<El> {
    let rows = p.rows();
    if rows.is_empty() {
        return None;
    }
    let mut list = col().key("rows").padding(6.0).gap(2.0);
    for (i, r) in rows.iter().enumerate() {
        list = list.child(line(p, r, i, i == p.picked, ink));
    }
    Some(list)
}

fn line(p: &Panel, r: &Row, i: usize, on: bool, ink: &Ink) -> El {
    let (title, detail) = row_text(p, r);
    let fg = if on { Color::WHITE } else { ink.text };
    let mut line = row().key(format!("row-{i}")).h(48.0).px(12.0).gap(12.0).radius(8.0).center_y()
        .on_press(move |s: &mut crate::App| s.dispatch(crate::panel::Event::Click(i)))
        .focusable(false) // the field keeps the keyboard: typing after a click still narrows
        .fill(if on { logo_blue().alpha(0.92) } else { Color::TRANSPARENT })
        .child(col().grow(1.0).shrink().gap(2.0)
            .child(text(title).font(type_::BODY).color(fg).truncate())
            .child(text(detail).font(type_::LABEL).color(if on { fg.alpha(0.8) } else { ink.muted }).truncate()));
    if let Some(badge) = badge(p, r) {
        line = line.child(text(badge).font(type_::LABEL).color(if on { fg } else { ink.muted }));
    }
    line
}

fn row_text(p: &Panel, r: &Row) -> (String, String) {
    match r {
        Row::Paper(i) => {
            let paper = &p.papers[*i];
            (paper.title.clone(), byline(&paper.authors, paper.year))
        }
        Row::SearchOnline(q) => (format!("Search online for “{q}”"), "Asks every paper source that's on".into()),
        Row::Candidate(i) => {
            let Phase::Found(f) = &p.phase else { return Default::default() };
            let c = &f.results[*i];
            (c.title.clone(), byline(&c.authors, c.year))
        }
        Row::SaveWithoutPdf => ("Save without PDF".into(), "Keeps its details and abstract; add the PDF later".into()),
        Row::OpenAdded(_) => match &p.phase {
            Phase::Added(paper) => (paper.title.clone(), "Open in PaperLab".into()),
            _ => Default::default(),
        },
        Row::OpenPaperLab => ("Open PaperLab".into(), UNREACHABLE.into()),
        Row::Workspace(i) => {
            let Some(w) = p.workspaces.as_ref().and_then(|all| all.get(*i)) else { return Default::default() };
            let last = if p.last_workspace.as_ref() == Some(&w.id) { " · used last" } else { "" };
            let mark = if chosen(p, &w.id) { "✓ " } else { "" };
            (format!("{mark}{}", w.name), format!("{} paper{}{last}", w.paper_count, if w.paper_count == 1 { "" } else { "s" }))
        }
        Row::FilingDone => {
            let Phase::Filing(f) = &p.phase else { return Default::default() };
            match f.chosen.len() {
                0 => {
                    let them = if f.paper_ids.len() == 1 { "it" } else { "them" };
                    (format!("Done: keep {them} in the library only"), "Or pick workspaces below first".into())
                }
                n => (format!("Put in {n} workspace{}", if n == 1 { "" } else { "s" }), p.chosen_names(f)),
            }
        }
        Row::CopyAnswer => ("Copy the answer".into(), "Plain text, with its [C1] markers".into()),
        Row::OpenAnswer => ("Open in PaperLab".into(), "The workspace's chat, with this answer and its passages".into()),
        Row::Source(i) => {
            let Phase::Answer(a) = &p.phase else { return Default::default() };
            let Some(c) = a.cited().into_iter().nth(*i) else { return Default::default() };
            let title = p.papers.iter().find(|x| x.id == c.paper_id).map(|x| x.title.clone());
            (title.unwrap_or_else(|| "A paper in this workspace".into()), format!("{} · p. {}", c.labels.join(", "), c.page))
        }
        Row::FoundPdf(i) => match p.inbox.as_ref().and_then(|x| x.found.get(*i)) {
            Some(f) => (f.title.clone(), "A free PDF was found for it: open it to read".into()),
            None => Default::default(),
        },
        Row::NewHits(i) => match p.inbox.as_ref().and_then(|x| x.searches.get(*i)) {
            Some(s) => (format!("“{}”", s.query), format!("{} new result{} · {}", s.count, if s.count == 1 { "" } else { "s" }, s.workspace)),
            None => Default::default(),
        },
        Row::Close(i) => {
            let Phase::Close(c) = &p.phase else { return Default::default() };
            let close = &c.papers[*i];
            (close.title.clone(), closeness(close))
        }
    }
}

fn badge(p: &Panel, r: &Row) -> Option<&'static str> {
    match (r, &p.phase) {
        (Row::Candidate(i), Phase::Found(f)) => Some(if f.results[*i].paper_id.is_some() { "In your library" } else { "Add ↵" }),
        (Row::Paper(_), _) if p.mode == Mode::Cite => Some("Copy ↵"),
        (Row::Paper(_), _) if p.mode == Mode::Note => Some("Write ↵"),
        (Row::Workspace(i), Phase::Filing(_)) => {
            let id = p.workspaces.as_ref().and_then(|all| all.get(*i)).map(|w| w.id.as_str()).unwrap_or_default();
            Some(if chosen(p, id) { "Picked ✓" } else { "Pick ↵" })
        }
        (Row::FilingDone, Phase::Filing(f)) => Some(if f.chosen.is_empty() { "Skip ↵" } else { "Put ↵" }),
        (Row::Workspace(_), _) => Some("Ask ↵"),
        (Row::CopyAnswer, _) => Some("Copy ↵"),
        (Row::Paper(_) | Row::OpenAdded(_) | Row::Close(_) | Row::OpenAnswer | Row::Source(_) | Row::FoundPdf(_) | Row::NewHits(_), _) => {
            Some("Open ↵")
        }
        _ => None,
    }
}


/// How close it is, where, and the passage that makes it so: "very close · p. 4 · “…”".
fn closeness(c: &Close) -> String {
    let mut parts = vec![c.label.clone()];
    if let Some(page) = c.page {
        parts.push(format!("p. {page}"));
    }
    let passage: String = c.passage.split_whitespace().collect::<Vec<_>>().join(" ");
    if !passage.is_empty() {
        parts.push(format!("“{passage}”"));
    }
    parts.join(" · ")
}

/// Filing: the workspace with this id is picked.
fn chosen(p: &Panel, id: &str) -> bool {
    matches!(&p.phase, Phase::Filing(f) if f.chosen.iter().any(|c| c == id))
}
