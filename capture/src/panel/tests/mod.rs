use super::*;
use crate::api::{Added, Close, Closeness, Format};
use crate::mode::Mode;
use crate::library::paper;
use serde_json::json;

mod ask;
mod drop;
mod filing;
mod inbox;
mod note;

fn shown_with_library() -> Panel {
    let mut p = Panel::default();
    assert_eq!(p.step(Event::Shown), vec![Effect::FetchPapers]);
    p.step(Event::Papers(Ok(vec![
        paper("a", "Attention Is All You Need", &["Ashish Vaswani"], 2017, "2026-01"),
        paper("b", "Graph attention networks", &["Petar Velickovic"], 2018, "2026-02"),
    ])));
    p
}

fn candidate(title: &str, paper_id: Option<&str>) -> Candidate {
    Candidate { title: title.into(), authors: vec![], year: Some(2017), paper_id: paper_id.map(Into::into),
                raw: json!({ "title": title }) }
}

fn typed(p: &mut Panel, text: &str) {
    for end in 1..=text.len() {
        p.step(Event::Query(text[..end].into()));
    }
}

#[test]
fn type_pick_and_open_a_library_paper() {
    let mut p = shown_with_library();
    typed(&mut p, "attention");
    assert_eq!(p.rows(), vec![Row::Paper(0), Row::Paper(1), Row::SearchOnline("attention".into())]);
    p.step(Event::Down);
    assert_eq!(p.step(Event::Submit), vec![Effect::Open("b".into()), Effect::Close]);
}

#[test]
fn up_wraps_and_an_empty_query_lists_newest() {
    let mut p = shown_with_library();
    assert_eq!(p.rows(), vec![Row::Paper(1), Row::Paper(0)]);
    p.step(Event::Up);
    assert_eq!(p.picked, 1);
}

#[test]
fn a_pasted_doi_looks_up_at_once_but_a_typed_one_waits_for_enter() {
    let mut p = shown_with_library();
    let fx = p.step(Event::Query("https://doi.org/10.48550/arXiv.1706.03762".into()));
    assert_eq!(fx, vec![Effect::Lookup { seq: 1, query: "10.48550/arXiv.1706.03762".into() }]);
    assert_eq!(p.phase, Phase::LookingUp("10.48550/arXiv.1706.03762".into()));

    let mut p = shown_with_library();
    typed(&mut p, "10.1234/abc");
    assert_eq!(p.phase, Phase::Library);
    assert_eq!(p.rows(), vec![Row::SearchOnline("10.1234/abc".into())]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Lookup { seq: 1, query: "10.1234/abc".into() }]);
}

#[test]
fn a_stale_lookup_answer_changes_nothing() {
    let mut p = shown_with_library();
    p.step(Event::Query("10.1234/first".into()));
    p.step(Event::Query("10.1234/second-one".into()));
    let found = Found { results: vec![candidate("First", None)], notices: vec![] };
    p.step(Event::Looked { seq: 1, result: Ok(found) });
    assert_eq!(p.phase, Phase::LookingUp("10.1234/second-one".into()));
}

#[test]
fn typing_while_adding_keeps_the_add_and_its_answer() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("New paper", None)], notices: vec![] }) });
    p.step(Event::Submit);
    assert_eq!(p.step(Event::Query("2401.12345x".into())), vec![]);
    let mut queued = paper("n", "New paper", &[], 2017, "2026");
    queued.status = "uploaded".into();
    assert_eq!(p.step(Event::AddDone { seq: p.seq, result: Ok(Added::Queued(queued)) }), vec![Effect::Poll("n".into())]);
}

#[test]
fn after_an_add_enter_acts_on_the_first_row_and_a_closed_panel_stops_following() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    let three = vec![candidate("A", None), candidate("B", None), candidate("C", None)];
    p.step(Event::Looked { seq: 1, result: Ok(Found { results: three, notices: vec![] }) });
    p.step(Event::Down);
    p.step(Event::Down);
    p.step(Event::Submit);
    p.step(Event::AddDone { seq: p.seq, result: Ok(Added::NoFreePdf("No free PDF.".into())) });
    assert_eq!(p.step(Event::Submit), vec![Effect::Add { seq: p.seq, candidate: candidate("C", None), save_without_pdf: true }]);

    p.step(Event::Closed);
    let mut queued = paper("c", "C", &[], 2017, "2026");
    queued.status = "uploaded".into();
    assert_eq!(p.step(Event::AddDone { seq: p.seq, result: Ok(Added::Queued(queued)) }), vec![]); // kept, not polled while hidden
}

#[test]
fn add_a_found_paper_and_follow_it_until_ready() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    let found = Found { results: vec![candidate("New paper", None)], notices: vec!["S2 is busy.".into()] };
    p.step(Event::Looked { seq: 1, result: Ok(found) });
    assert_eq!(p.rows(), vec![Row::Candidate(0)]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Add { seq: p.seq, candidate: candidate("New paper", None), save_without_pdf: false }]);

    let mut queued = paper("n", "New paper", &[], 2017, "2026");
    queued.status = "uploaded".into();
    assert_eq!(p.step(Event::AddDone { seq: p.seq, result: Ok(Added::Queued(queued.clone())) }), vec![Effect::Poll("n".into())]);
    queued.status = "embedding".into();
    assert_eq!(p.step(Event::Status { id: "n".into(), result: Ok(queued.clone()) }), vec![Effect::Poll("n".into())]);
    queued.status = "ready".into();
    assert_eq!(p.step(Event::Status { id: "n".into(), result: Ok(queued) }), vec![]);
    assert_eq!(p.rows(), vec![Row::OpenAdded("n".into())]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Open("n".into()), Effect::Close]);
}

#[test]
fn closing_stops_the_polling() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("New", None)], notices: vec![] }) });
    p.step(Event::Submit);
    let mut queued = paper("n", "New", &[], 2017, "2026");
    queued.status = "uploaded".into();
    p.step(Event::AddDone { seq: p.seq, result: Ok(Added::Queued(queued.clone())) });
    p.step(Event::Closed);
    assert_eq!(p.step(Event::Status { id: "n".into(), result: Ok(queued) }), vec![]);
}

#[test]
fn a_candidate_already_held_opens_instead_of_adding() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("Held", Some("a"))], notices: vec![] }) });
    assert_eq!(p.step(Event::Submit), vec![Effect::Open("a".into()), Effect::Close]);
}

#[test]
fn no_free_pdf_offers_save_without_pdf() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("Paywalled", None)], notices: vec![] }) });
    p.step(Event::Submit);
    p.step(Event::AddDone { seq: p.seq, result: Ok(Added::NoFreePdf("No free PDF was found for this paper.".into())) });
    assert_eq!(p.rows(), vec![Row::SaveWithoutPdf]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Add { seq: p.seq, candidate: candidate("Paywalled", None), save_without_pdf: true }]);
}

#[test]
fn offline_offers_to_open_paperlab_and_recovers() {
    let mut p = Panel::default();
    p.step(Event::Shown);
    p.step(Event::Papers(Err(ApiError::Unreachable)));
    assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
    assert_eq!(p.step(Event::Submit), vec![Effect::OpenPaperLab, Effect::Close]);
    p.step(Event::Papers(Ok(vec![paper("a", "A", &[], 2020, "2026")])));
    assert_eq!(p.rows(), vec![Row::Paper(0)]);
}

#[test]
fn a_lookup_error_shows_paperlabs_sentence() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.step(Event::Looked { seq: 1, result: Err(ApiError::Said("No paper source that can look this up is on.".into())) });
    assert_eq!(p.phase, Phase::Failed("No paper source that can look this up is on.".into()));
}

fn close(id: &str, label: &str) -> Close {
    Close { paper_id: id.into(), title: format!("Paper {id}"), year: Some(2020), label: label.into(),
            passage: "a passage".into(), page: Some(3) }
}

#[test]
fn tab_walks_the_modes_and_the_query_stays_for_the_next_one() {
    let mut p = shown_with_library();
    typed(&mut p, "graph");
    p.step(Event::NextMode { forward: true });
    assert_eq!((p.mode, p.query.as_str()), (Mode::Cite, "graph"));
    assert_eq!(p.rows(), vec![Row::Paper(1)], "Cite filters the library by the same text");
    p.step(Event::NextMode { forward: false });
    assert_eq!(p.mode, Mode::Find);
}

#[test]
fn a_reopened_panel_keeps_its_mode() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Novelty));
    p.step(Event::Closed);
    p.step(Event::Shown);
    assert_eq!(p.mode, Mode::Novelty);
}

#[test]
fn modes_wait_while_an_add_is_in_flight() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.step(Event::Looked { seq: 1, result: Ok(Found { results: vec![candidate("New", None)], notices: vec![] }) });
    p.step(Event::Submit);
    assert!(matches!(p.phase, Phase::Adding(_)));
    p.step(Event::Mode(Mode::Cite));
    assert_eq!(p.mode, Mode::Find);
}

#[test]
fn cite_copies_apa_on_enter_and_bibtex_on_command_enter_then_closes() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Cite));
    typed(&mut p, "attention");
    let apa = Effect::Cite { seq: 1, paper_id: "a".into(), title: "Attention Is All You Need".into(), format: Format::Apa };
    assert_eq!(p.step(Event::Submit), vec![apa]);
    p.step(Event::Query("attention".into())); // the user moved on: the APA copy is dropped
    p.step(Event::Down);
    let bibtex = Effect::Cite { seq: 2, paper_id: "b".into(), title: "Graph attention networks".into(), format: Format::Bibtex };
    assert_eq!(p.step(Event::SubmitAlt), vec![bibtex]);
    let what = "the BibTeX entry of “Graph attention networks”".to_owned();
    assert_eq!(p.step(Event::Copied { seq: 2, what, result: Ok(()) }), vec![Effect::CloseSoon(2)]);
    assert_eq!(p.phase, Phase::Copied("Copied the BibTeX entry of “Graph attention networks”.".into()));
}

#[test]
fn a_failed_copy_says_why_and_stays_open() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Cite));
    let seq = match p.step(Event::Submit).as_slice() { [Effect::Cite { seq, .. }] => *seq, other => panic!("{other:?}") };
    let failed = Event::Copied { seq, what: "x".into(), result: Err(ApiError::Said("No such paper.".into())) };
    assert_eq!(p.step(failed), vec![]);
    assert_eq!(p.phase, Phase::Failed("No such paper.".into()));
}

#[test]
fn done_before_searches_on_enter_and_opens_a_close_paper() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Novelty));
    assert_eq!(p.step(Event::Submit), vec![], "nothing typed, nothing asked");
    typed(&mut p, "graph attention for citations ");
    assert_eq!(p.step(Event::Submit), vec![Effect::Novelty { seq: 1, text: "graph attention for citations".into() }]);
    assert_eq!(p.step(Event::Submit), vec![], "one search at a time");
    let found = Closeness { papers: vec![close("x", "very close"), close("y", "related")], note: String::new() };
    p.step(Event::Novelty { seq: 1, result: Ok(found) });
    assert_eq!(p.rows(), vec![Row::Close(0), Row::Close(1)]);
    p.step(Event::Down);
    assert_eq!(p.step(Event::Submit), vec![Effect::Open("y".into()), Effect::Close]);
}

#[test]
fn an_answer_for_text_since_edited_is_dropped() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Novelty));
    typed(&mut p, "idea");
    p.step(Event::Submit);
    p.step(Event::Query("idea, refined".into()));
    p.step(Event::Novelty { seq: 1, result: Ok(Closeness { papers: vec![close("x", "related")], note: String::new() }) });
    assert_eq!((p.phase.clone(), p.rows()), (Phase::Library, vec![]));
}

#[test]
fn done_before_offline_offers_to_open_paperlab() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Novelty));
    typed(&mut p, "idea");
    p.step(Event::Submit);
    p.step(Event::Novelty { seq: 1, result: Err(ApiError::Unreachable) });
    assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
}

fn adding(p: &mut Panel, title: &str) -> Vec<Effect> {
    p.step(Event::Query("2401.12345".into()));
    let seq = p.seq;
    p.step(Event::Looked { seq, result: Ok(Found { results: vec![candidate(title, None)], notices: vec![] }) });
    p.step(Event::Submit)
}

#[test]
fn an_add_under_way_holds_through_a_reopen_and_a_wrong_seq_changes_nothing() {
    let mut p = shown_with_library();
    let first = adding(&mut p, "A");
    let [Effect::Add { seq: a, .. }] = first.as_slice() else { panic!("{first:?}") };
    let a = *a;
    p.step(Event::Closed);
    p.step(Event::Shown);
    assert_eq!(adding(&mut p, "B"), vec![], "B waits for A");
    let late = Paper { id: "a".into(), ..paper("a", "A", &[], 2020, "x") };
    assert_eq!(p.step(Event::AddDone { seq: a + 1, result: Ok(Added::Queued(late.clone())) }), vec![]);
    assert!(matches!(&p.phase, Phase::Adding(c) if c.title == "A"));
    p.step(Event::AddDone { seq: a, result: Ok(Added::Queued(late)) });
    assert!(matches!(&p.phase, Phase::Added(x) if x.id == "a"));
}

fn cite_enter(p: &mut Panel) -> u64 {
    p.step(Event::Mode(Mode::Cite));
    match p.step(Event::Submit).as_slice() {
        [Effect::Cite { seq, .. }] => *seq,
        other => panic!("{other:?}"),
    }
}

#[test]
fn enter_twice_copies_once() {
    let mut p = shown_with_library();
    cite_enter(&mut p);
    assert_eq!(p.step(Event::SubmitAlt), vec![], "the first copy is still under way");
}

#[test]
fn a_copy_answering_after_a_mode_switch_changes_nothing() {
    let mut p = shown_with_library();
    let seq = cite_enter(&mut p);
    p.step(Event::Mode(Mode::Find));
    assert_eq!(p.step(Event::Copied { seq, what: "it".into(), result: Ok(()) }), vec![]);
    assert_eq!(p.phase, Phase::Library);
}

#[test]
fn the_panel_closes_after_a_copy_only_if_the_user_has_not_moved_on() {
    let mut p = shown_with_library();
    let seq = cite_enter(&mut p);
    assert_eq!(p.step(Event::Copied { seq, what: "it".into(), result: Ok(()) }), vec![Effect::CloseSoon(seq)]);
    assert_eq!(p.step(Event::CloseNow(seq + 1)), vec![], "another copy's timer");
    assert_eq!(p.step(Event::CloseNow(seq)), vec![Effect::Close]);
    let mut moved = shown_with_library();
    let seq = cite_enter(&mut moved);
    moved.step(Event::Copied { seq, what: "it".into(), result: Ok(()) });
    moved.step(Event::Query("other".into()));
    assert_eq!(moved.step(Event::CloseNow(seq)), vec![]);
}

#[test]
fn the_librarys_own_error_sentence_is_kept_for_the_status_line() {
    let mut p = Panel::default();
    p.step(Event::Shown);
    p.step(Event::Papers(Err(ApiError::Said("The database is migrating.".into()))));
    assert_eq!(p.library_error.as_deref(), Some("The database is migrating."));
    p.step(Event::Papers(Ok(vec![])));
    assert_eq!(p.library_error, None);
}

#[test]
fn command_l_looks_up_papers_like_the_picked_one_as_candidates_to_add() {
    let mut p = shown_with_library();
    typed(&mut p, "graph");
    let seq = match p.step(Event::Similar).as_slice() {
        [Effect::Similar { seq, paper_id }] if paper_id == "b" => *seq,
        other => panic!("{other:?}"),
    };
    assert_eq!(p.phase, Phase::LookingUp("papers like “Graph attention networks”".into()));
    let found = Found { results: vec![candidate("Graph transformers", None)], notices: vec![] };
    p.step(Event::Looked { seq, result: Ok(found) });
    assert_eq!(p.rows(), vec![Row::Candidate(0)], "Enter adds it, as a lookup's result");
}

#[test]
fn command_l_needs_a_paper_picked_in_find() {
    let mut p = shown_with_library();
    typed(&mut p, "2401.12345");
    assert_eq!(p.step(Event::Similar), vec![], "Search online isn't a paper");
    p.step(Event::Mode(Mode::Cite));
    assert_eq!(p.step(Event::Similar), vec![]);
}

#[test]
fn command_l_works_on_the_paper_just_added_but_waits_for_an_add_in_flight() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    p.phase = Phase::Adding(candidate("Sparse attention", None));
    assert_eq!(p.step(Event::Similar), vec![], "an add in flight keeps the panel");
    let seq = p.seq;
    p.step(Event::AddDone { seq, result: Ok(Added::Queued(paper("n", "Sparse attention", &[], 2024, "2026-03"))) });
    assert!(matches!(p.step(Event::Similar).as_slice(), [Effect::Similar { paper_id, .. }] if paper_id == "n"));
}
