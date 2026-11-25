use super::*;
use crate::api::Added;
use crate::library::paper;
use serde_json::json;

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
    assert_eq!(p.step(Event::AddDone(Ok(Added::Queued(queued)))), vec![Effect::Poll("n".into())]);
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
    p.step(Event::AddDone(Ok(Added::NoFreePdf("No free PDF.".into()))));
    assert_eq!(p.step(Event::Submit), vec![Effect::Add { candidate: candidate("C", None), save_without_pdf: true }]);

    p.step(Event::Closed);
    let mut queued = paper("c", "C", &[], 2017, "2026");
    queued.status = "uploaded".into();
    assert_eq!(p.step(Event::AddDone(Ok(Added::Queued(queued)))), vec![]); // kept, not polled while hidden
}

#[test]
fn add_a_found_paper_and_follow_it_until_ready() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    let found = Found { results: vec![candidate("New paper", None)], notices: vec!["S2 is busy.".into()] };
    p.step(Event::Looked { seq: 1, result: Ok(found) });
    assert_eq!(p.rows(), vec![Row::Candidate(0)]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Add { candidate: candidate("New paper", None), save_without_pdf: false }]);

    let mut queued = paper("n", "New paper", &[], 2017, "2026");
    queued.status = "uploaded".into();
    assert_eq!(p.step(Event::AddDone(Ok(Added::Queued(queued.clone())))), vec![Effect::Poll("n".into())]);
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
    p.step(Event::AddDone(Ok(Added::Queued(queued.clone()))));
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
    p.step(Event::AddDone(Ok(Added::NoFreePdf("No free PDF was found for this paper.".into()))));
    assert_eq!(p.rows(), vec![Row::SaveWithoutPdf]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Add { candidate: candidate("Paywalled", None), save_without_pdf: true }]);
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
