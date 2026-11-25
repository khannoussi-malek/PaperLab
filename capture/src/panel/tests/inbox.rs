//! Inbox: free PDFs found and saved searches with new results.

use super::*;
use crate::api::{FoundPdf, Inbox, NewHits};

fn inbox() -> Inbox {
    Inbox {
        found: vec![FoundPdf { id: "e1".into(), paper_id: "p1".into(), title: "Paywalled no more".into() }],
        searches: vec![NewHits { workspace_id: "w1".into(), workspace: "Thesis".into(), query: "sparse attention".into(), count: 4 }],
    }
}

fn in_inbox() -> Panel {
    let mut p = shown_with_library();
    assert_eq!(p.step(Event::Mode(Mode::Inbox)), vec![Effect::FetchInbox]);
    p.step(Event::Inbox(Ok(inbox())));
    p
}

#[test]
fn the_inbox_lists_finds_then_searches_and_counts_them() {
    let p = in_inbox();
    assert_eq!(p.rows(), vec![Row::FoundPdf(0), Row::NewHits(0)]);
    assert_eq!(p.inbox.as_ref().map(Inbox::count), Some(2));
}

#[test]
fn enter_on_a_find_marks_it_seen_and_opens_the_paper() {
    let mut p = in_inbox();
    assert_eq!(p.step(Event::Submit), vec![Effect::FoundSeen("e1".into()), Effect::Open("p1".into()), Effect::Close]);
}

#[test]
fn enter_on_new_results_opens_the_workspace_search() {
    let mut p = in_inbox();
    p.step(Event::Down);
    assert_eq!(p.step(Event::Submit), vec![Effect::OpenWorkspace { id: "w1".into(), tab: "search" }, Effect::Close]);
}

#[test]
fn the_inbox_is_fetched_on_reopen_and_kept_meanwhile_and_offline_offers_paperlab() {
    let mut p = in_inbox();
    p.step(Event::Closed);
    assert_eq!(p.step(Event::Shown), vec![Effect::FetchPapers, Effect::FetchInbox]);
    assert_eq!(p.rows().len(), 2, "the last list shows until the new one comes");
    let mut off = shown_with_library();
    off.step(Event::Mode(Mode::Inbox));
    off.step(Event::Inbox(Err(ApiError::Unreachable)));
    assert_eq!(off.rows(), vec![Row::OpenPaperLab]);
}
