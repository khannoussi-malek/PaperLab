//! PDFs dropped on the floating paper.

use super::*;
use crate::panel::drop::NOT_A_PDF;

fn ingesting(id: &str) -> Paper {
    Paper { status: "embedding".into(), ..paper(id, &format!("Paper {id}"), &[], 2024, "x") }
}

fn drop_two(p: &mut Panel) -> u64 {
    match p.step(Event::Dropped(vec!["/a.pdf".into(), "/b.pdf".into()])).as_slice() {
        [Effect::Upload { seq, paths }] if paths.len() == 2 => *seq,
        other => panic!("{other:?}"),
    }
}

#[test]
fn a_drop_uploads_in_find_and_follows_the_last_paper() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Cite));
    let seq = drop_two(&mut p);
    assert_eq!((p.mode, &p.phase), (Mode::Find, &Phase::Uploading { count: 2 }));
    let fx = p.step(Event::Uploaded { seq, results: vec![Ok(ingesting("a")), Ok(ingesting("b"))] });
    assert_eq!(fx, vec![Effect::Poll("b".into())]);
    assert!(matches!(&p.phase, Phase::Added(x) if x.id == "b"));
    assert_eq!(p.upload_note.as_deref(), Some("Added 2 PDFs; following the last one."));
}

#[test]
fn a_partly_failed_drop_says_how_many_and_why() {
    let mut p = shown_with_library();
    let seq = drop_two(&mut p);
    let results = vec![Err(ApiError::Said("'b.pdf' is not a PDF".into())), Ok(ingesting("a"))];
    p.step(Event::Uploaded { seq, results });
    assert_eq!(p.upload_note.as_deref(), Some("Added 1 of 2 PDFs ('b.pdf' is not a PDF); following the last one."));
    let mut all = shown_with_library();
    let seq = drop_two(&mut all);
    all.step(Event::Uploaded { seq, results: vec![Err(ApiError::Unreachable), Err(ApiError::Unreachable)] });
    assert_eq!(all.rows(), vec![Row::OpenPaperLab]);
}

#[test]
fn one_upload_at_a_time_and_a_stale_answer_changes_nothing() {
    let mut p = shown_with_library();
    let seq = drop_two(&mut p);
    assert_eq!(p.step(Event::Dropped(vec!["/c.pdf".into()])), vec![]);
    p.step(Event::Query("x".into()));
    assert_eq!(p.step(Event::Uploaded { seq: seq + 7, results: vec![Ok(ingesting("z"))] }), vec![]);
}

#[test]
fn something_else_dropped_says_what_to_do() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Ask));
    p.step(Event::DropRefused);
    assert_eq!((p.mode, p.phase.clone()), (Mode::Find, Phase::Failed(NOT_A_PDF.into())));
}
