//! PDFs dropped on the floating paper.

use super::*;
use crate::api::Added;
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

#[test]
fn reopening_mid_upload_keeps_it_and_follows_its_paper() {
    let mut p = shown_with_library();
    let seq = drop_two(&mut p);
    p.step(Event::Closed);
    p.step(Event::Shown);
    assert_eq!(p.phase, Phase::Uploading { count: 2 });
    assert_eq!(p.step(Event::Dropped(vec!["/c.pdf".into()])), vec![], "still one at a time");
    assert_eq!(p.step(Event::Uploaded { seq, results: vec![Ok(ingesting("a"))] }), vec![Effect::Poll("a".into())]);
}

#[test]
fn reopening_mid_add_keeps_it_too() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    let seq = p.seq;
    p.step(Event::Looked { seq, result: Ok(Found { results: vec![candidate("New", None)], notices: vec![] }) });
    p.step(Event::Submit);
    p.step(Event::Closed);
    p.step(Event::Shown);
    let seq = p.seq;
    assert_eq!(p.step(Event::AddDone { seq, result: Ok(Added::Queued(ingesting("n"))) }), vec![Effect::Poll("n".into())]);
}

#[test]
fn the_drop_note_goes_with_the_next_add_and_a_refused_drop_stops_following() {
    let mut p = shown_with_library();
    let seq = drop_two(&mut p);
    p.step(Event::Uploaded { seq, results: vec![Ok(ingesting("a")), Ok(ingesting("b"))] });
    p.step(Event::DropRefused);
    assert_eq!(p.step(Event::Status { id: "b".into(), result: Ok(ingesting("b")) }), vec![], "no longer followed");
    assert_eq!(p.phase, Phase::Failed(NOT_A_PDF.into()));
    p.step(Event::Query("graph".into()));
    assert_eq!(p.upload_note, None);
}
