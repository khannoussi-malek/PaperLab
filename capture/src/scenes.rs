//! Fixed states for `--snap` stills; they set the state through `Panel::step` and drop its effects.

use crate::App;
use crate::api::{Added, Candidate, Close, Closeness, Format, Found, FoundPdf, Inbox, NewHits, Said, Source, Workspace};
use crate::library::Paper;
use crate::mode::Mode;
use crate::panel::{Event, Panel};

const QUESTION: &str = "How do these papers handle documents longer than the context window?";
const IDEA: &str = "Sparse attention lets long papers fit a small model's context";

pub const ALL: &[(&str, fn(&mut App))] = &[
    ("library", |s| set(s, "", library_shown())),
    ("typed", |s| { let mut p = library_shown(); p.step(Event::Query("transformer".into())); set(s, "transformer", p) }),
    ("looking-up", |s| set(s, "10.48550/arXiv.1706.03762", looked_up(None))),
    ("found", |s| set(s, "10.48550/arXiv.1706.03762", looked_up(Some(Ok(found()))))),
    ("adding", |s| set(s, "2401.12345", added(None))),
    ("added", |s| set(s, "2401.12345", added(Some(Added::Queued(paper("n", "Retrieval-augmented reading of long papers", "embedding")))))),
    ("no-free-pdf", |s| set(s, "2401.12345", added(Some(Added::NoFreePdf("No free PDF was found for this paper. Open its page, download the PDF and use Upload PDFs.".into()))))),
    ("cite", |s| { let mut p = in_mode(Mode::Cite); p.step(Event::Query("attention".into())); set(s, "attention", p) }),
    ("copied", |s| {
        let mut p = in_mode(Mode::Cite);
        p.step(Event::Query("attention".into()));
        p.step(Event::Submit);
        let what = format!("{} of “Attention Is All You Need”", Format::Apa.label());
        p.step(Event::Copied { seq: p.seq, what, result: Ok(()) });
        set(s, "attention", p)
    }),
    ("dropped", |s| set(s, "", dropped())),
    ("note", |s| { let mut p = in_mode(Mode::Note); p.step(Event::Query("retrieval".into())); set(s, "retrieval", p) }),
    ("note-writing", |s| set(s, NOTE, note_writing())),
    ("filing", |s| set(s, "", filing())),
    ("inbox", |s| set(s, "", inbox())),
    ("ask", |s| set(s, QUESTION, ask_typed())),
    ("answering", |s| set(s, QUESTION, answer(false))),
    ("answered", |s| set(s, QUESTION, answer(true))),
    ("searching", |s| { let mut p = novelty_typed(); p.step(Event::Submit); set(s, IDEA, p) }),
    ("done-before", |s| set(s, IDEA, done_before())),
    ("offline", |s| { let mut p = Panel::default(); p.step(Event::Papers(Err(crate::api::ApiError::Unreachable))); set(s, "", p) }),
];

fn set(s: &mut App, query: &str, panel: Panel) {
    s.query = crate::focused(query);
    s.panel = panel;
}

fn paper(id: &str, title: &str, status: &str) -> Paper {
    Paper { id: id.into(), title: title.into(), authors: vec!["Ana Lopez".into(), "Wei Zhang".into(), "Sam Okafor".into()],
            year: Some(2024), doi: None, status: status.into(), status_error: None, created_at: format!("2026-11-{id}") }
}

fn library_shown() -> Panel {
    let mut p = Panel::default();
    p.step(Event::Shown);
    p.step(Event::Papers(Ok(vec![
        paper("01", "Attention Is All You Need", "ready"),
        paper("02", "BERT: Pre-training of Deep Bidirectional Transformers", "ready"),
        paper("03", "Retrieval-Augmented Generation for Knowledge-Intensive NLP", "ready"),
        paper("04", "Scaling Laws for Neural Language Models", "ready"),
        paper("05", "An Image is Worth 16x16 Words: Transformers for Image Recognition", "ready"),
    ])));
    p
}

fn in_mode(mode: Mode) -> Panel {
    let mut p = library_shown();
    p.step(Event::Mode(mode));
    p
}

const NOTE: &str = "Their retriever is frozen: try fine-tuning it on our corpus";

fn filing() -> Panel {
    let mut p = library_shown();
    p.step(Event::Query("retrieval".into()));
    p.step(Event::SubmitAlt);
    p.step(Event::Workspaces(Ok(vec![
        Workspace { id: "w1".into(), name: "Thesis: long documents".into(), paper_count: 24 },
        Workspace { id: "w2".into(), name: "Reading group".into(), paper_count: 7 },
        Workspace { id: "w3".into(), name: "RAG survey".into(), paper_count: 41 },
    ])));
    p
}

fn note_writing() -> Panel {
    let mut p = in_mode(Mode::Note);
    p.step(Event::Query("retrieval".into()));
    p.step(Event::Submit);
    p.step(Event::Query(NOTE.into()));
    p
}

fn dropped() -> Panel {
    let mut p = library_shown();
    p.step(Event::Dropped(vec!["/Downloads/long-context.pdf".into(), "/Downloads/sparse.pdf".into()]));
    let seq = p.seq;
    let results = vec![Ok(paper("a", "Sparse Attention for Long Documents", "uploaded")), Ok(paper("b", "Reading Long Papers with Small Models", "extracting"))];
    p.step(Event::Uploaded { seq, results });
    p
}

fn inbox() -> Panel {
    let mut p = in_mode(Mode::Inbox);
    let found = |id: &str, title: &str| FoundPdf { id: id.into(), paper_id: id.into(), title: title.into() };
    let hits = |query: &str, count, workspace: &str| NewHits {
        workspace_id: "w".into(), workspace: workspace.into(), query: query.into(), count,
    };
    p.step(Event::Inbox(Ok(Inbox {
        found: vec![found("f1", "Longformer: The Long-Document Transformer")],
        searches: vec![hits("sparse attention long documents", 4, "Thesis: long-context reading"), hits("retrieval augmented summarisation", 1, "Survey draft")],
    })));
    p
}

fn ask_typed() -> Panel {
    let mut p = in_mode(Mode::Ask);
    let workspace = |id: &str, name: &str, paper_count| Workspace { id: id.into(), name: name.into(), paper_count };
    p.step(Event::Workspaces(Ok(vec![
        workspace("w1", "Thesis: long-context reading", 42),
        workspace("w2", "Reading group, spring", 9),
        workspace("w3", "Survey draft", 118),
    ])));
    p.step(Event::Query(QUESTION.into()));
    p
}

fn answer(done: bool) -> Panel {
    let mut p = ask_typed();
    p.step(Event::Submit);
    let seq = p.seq;
    let sources = vec![
        Source { label: "C1".into(), paper_id: "03".into(), page: 4 },
        Source { label: "C2".into(), paper_id: "01".into(), page: 6 },
        Source { label: "C3".into(), paper_id: "03".into(), page: 9 },
    ];
    p.step(Event::Heard { seq, result: Ok(Said::Sources(sources)) });
    let text = "Two routes recur. Retrieval keeps the prompt short: the document is split into passages and only the \
                closest few are read [C1], which scales to any length but can miss an answer spread across sections \
                [C3]. Sparse attention instead lets the model read far more at once [C2]; it costs more memory and \
                still has a ceiling. Your workspace has no paper comparing the two on the same documents.";
    let text = if done { text } else { &text[..160] };
    p.step(Event::Heard { seq, result: Ok(Said::Token(text.into())) });
    if done { p.step(Event::Heard { seq, result: Ok(Said::Done) }); }
    p
}

fn novelty_typed() -> Panel {
    let mut p = in_mode(Mode::Novelty);
    p.step(Event::Query(IDEA.into()));
    p
}

fn done_before() -> Panel {
    let mut p = novelty_typed();
    p.step(Event::Submit);
    let close = |id: &str, title: &str, label: &str, page, passage: &str| Close {
        paper_id: id.into(), title: title.into(), year: Some(2020), label: label.into(), passage: passage.into(), page,
    };
    let papers = vec![
        close("01", "Longformer: The Long-Document Transformer", "very close", Some(2),
              "an attention mechanism that scales linearly with sequence length, making it easy to process documents"),
        close("04", "Scaling Laws for Neural Language Models", "related", Some(7), "performance depends on context"),
        close("02", "BERT: Pre-training of Deep Bidirectional Transformers", "distant", None, ""),
    ];
    let note = "Only your own library was searched: nothing close here doesn't mean nobody has done it.".into();
    p.step(Event::Novelty { seq: 1, result: Ok(Closeness { papers, note }) });
    p
}

fn candidate(title: &str, paper_id: Option<&str>) -> Candidate {
    Candidate { title: title.into(), authors: vec!["Ashish Vaswani".into(), "Noam Shazeer".into(), "Niki Parmar".into()],
                year: Some(2017), paper_id: paper_id.map(Into::into), raw: serde_json::json!({ "title": title }) }
}

fn found() -> Found {
    Found { results: vec![candidate("Attention Is All You Need", None)],
            notices: vec!["Semantic Scholar is busy or unreachable.".into()] }
}

fn looked_up(answer: Option<Result<Found, crate::api::ApiError>>) -> Panel {
    let mut p = library_shown();
    p.step(Event::Query("10.48550/arXiv.1706.03762".into()));
    if let Some(result) = answer { p.step(Event::Looked { seq: 1, result }); }
    p
}

fn added(answer: Option<Added>) -> Panel {
    let mut p = library_shown();
    p.step(Event::Query("2401.12345".into()));
    let found = Found { results: vec![candidate("Retrieval-augmented reading of long papers", None)], notices: vec![] };
    p.step(Event::Looked { seq: 1, result: Ok(found) });
    p.step(Event::Submit);
    if let Some(answer) = answer { p.step(Event::AddDone { seq: 2, result: Ok(answer) }); }
    p
}
