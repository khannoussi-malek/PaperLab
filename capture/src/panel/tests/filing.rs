//! Filing papers in workspaces: after a drop, or ⌘↵ on a paper in Find. Several workspaces can be picked.

use super::*;
use crate::api::Workspace;

fn workspace(id: &str, name: &str) -> Workspace {
    Workspace { id: id.into(), name: name.into(), paper_count: 2 }
}

fn workspaces() -> Vec<Workspace> {
    vec![workspace("w1", "Thesis"), workspace("w2", "Reading group"), workspace("w3", "RAG survey")]
}

fn filing_graph_attention() -> Panel {
    let mut p = shown_with_library();
    typed(&mut p, "graph");
    assert_eq!(p.step(Event::SubmitAlt), vec![Effect::FetchWorkspaces]);
    p.step(Event::Workspaces(Ok(workspaces())));
    p
}

fn chosen(p: &Panel) -> Vec<String> {
    match &p.phase {
        Phase::Filing(f) => f.chosen.clone(),
        other => panic!("{other:?}"),
    }
}

#[test]
fn enter_picks_several_workspaces_and_the_done_row_puts_the_paper_in_all_of_them() {
    let mut p = filing_graph_attention();
    assert!(matches!(&p.phase, Phase::Filing(f) if f.paper_ids == ["b"] && f.what == "“Graph attention networks”"));
    assert_eq!(p.query, "", "the field now narrows the workspaces");
    assert_eq!(p.rows(), vec![Row::FilingDone, Row::Workspace(0), Row::Workspace(1), Row::Workspace(2)]);
    assert_eq!(p.picked, 1, "the first workspace, so Enter picks it");
    assert_eq!(p.step(Event::Submit), vec![]);
    p.step(Event::Down);
    p.step(Event::Down);
    p.step(Event::Submit);
    assert_eq!(chosen(&p), ["w1", "w3"]);
    p.step(Event::Up);
    p.step(Event::Up);
    p.step(Event::Submit);
    assert_eq!(chosen(&p), ["w3"], "Enter again unpicks");
    p.step(Event::Submit);
    p.picked = 0;
    let seq = match p.step(Event::Submit).as_slice() {
        [Effect::PutInWorkspaces { seq, workspace_ids, paper_ids }] => {
            assert_eq!((workspace_ids.as_slice(), paper_ids.as_slice()), (["w3".to_owned(), "w1".to_owned()].as_slice(), ["b".to_owned()].as_slice()));
            *seq
        }
        other => panic!("{other:?}"),
    };
    assert_eq!(p.step(Event::Submit), vec![], "Enter again waits for the answer");
    assert_eq!(p.step(Event::Put { seq, result: Ok(()) }), vec![Effect::CloseSoon(seq)]);
    assert_eq!(p.phase, Phase::Filed("Put “Graph attention networks” in “RAG survey” and “Thesis”.".into()));
    assert_eq!(p.step(Event::CloseNow(seq)), vec![Effect::Close]);
    assert_eq!(p.last_workspace.as_deref(), Some("w3"), "the first picked comes first next time, in Ask too");
}

#[test]
fn the_done_row_with_nothing_picked_leaves_the_paper_in_the_library() {
    let mut p = filing_graph_attention();
    p.picked = 0;
    assert_eq!(p.step(Event::Submit), vec![Effect::Close]);
}

#[test]
fn a_click_on_a_row_picks_it_and_acts_as_enter() {
    let mut p = filing_graph_attention();
    p.step(Event::Click(2));
    assert_eq!((p.picked, chosen(&p)), (2, vec!["w2".to_owned()]));
    assert!(matches!(p.step(Event::Click(0)).as_slice(), [Effect::PutInWorkspaces { .. }]));
    assert_eq!(p.step(Event::Click(9)), vec![], "no such row");
}

#[test]
fn typing_narrows_the_workspaces_and_keeps_what_was_picked() {
    let mut p = filing_graph_attention();
    p.step(Event::Submit); // Thesis
    p.step(Event::Query("read".into()));
    assert_eq!((p.rows(), p.picked), (vec![Row::FilingDone, Row::Workspace(1)], 1));
    p.step(Event::Submit);
    assert_eq!(chosen(&p), ["w1", "w2"]);
}

#[test]
fn a_refused_put_keeps_the_picks_with_why_and_a_stray_answer_changes_nothing() {
    let mut p = filing_graph_attention();
    p.step(Event::Submit);
    p.picked = 0;
    let Some(Effect::PutInWorkspaces { seq, .. }) = p.step(Event::Submit).pop() else { panic!() };
    assert_eq!(p.step(Event::Put { seq: seq + 1, result: Ok(()) }), vec![]);
    p.step(Event::Put { seq, result: Err(ApiError::Said("w1 not found".into())) });
    assert!(matches!(&p.phase, Phase::Filing(f) if f.error.as_deref() == Some("w1 not found") && f.putting.is_none()));
    assert_eq!(chosen(&p), ["w1"]);
    assert!(matches!(p.step(Event::Submit).as_slice(), [Effect::PutInWorkspaces { .. }]), "try again");
}

#[test]
fn the_paper_just_added_can_be_filed_too_and_a_lookup_row_cannot() {
    let mut p = shown_with_library();
    p.step(Event::Query("2401.12345".into()));
    assert_eq!(p.step(Event::SubmitAlt), vec![], "Search online isn't a paper");
    let seq = p.seq;
    p.phase = Phase::Adding(candidate("Sparse attention", None));
    p.step(Event::AddDone { seq, result: Ok(Added::Queued(paper("n", "Sparse attention", &[], 2024, "2026-03"))) });
    assert!(matches!(p.phase, Phase::Added(_)));
    assert_eq!(p.step(Event::SubmitAlt), vec![Effect::FetchWorkspaces]);
    assert!(matches!(&p.phase, Phase::Filing(f) if f.paper_ids == ["n"]));
}

#[test]
fn no_workspace_yet_leaves_only_done_and_offline_offers_paperlab() {
    let mut p = shown_with_library();
    typed(&mut p, "graph");
    p.step(Event::SubmitAlt);
    p.step(Event::Workspaces(Ok(vec![])));
    assert_eq!(p.rows(), vec![Row::FilingDone]);
    assert_eq!(p.step(Event::Submit), vec![Effect::Close]);
    let mut off = shown_with_library();
    typed(&mut off, "graph");
    off.step(Event::SubmitAlt);
    off.step(Event::Workspaces(Err(ApiError::Unreachable)));
    assert_eq!(off.rows(), vec![Row::OpenPaperLab]);
}

#[test]
fn a_put_under_way_holds_through_tab_and_a_reopen_and_its_answer_lands() {
    let mut p = filing_graph_attention();
    p.step(Event::Submit);
    p.picked = 0;
    let Some(Effect::PutInWorkspaces { seq, .. }) = p.step(Event::Submit).pop() else { panic!() };
    assert_eq!(p.step(Event::NextMode { forward: true }), vec![], "Tab waits for the put");
    p.step(Event::Closed);
    p.mode = Mode::Ask; // a bubble reopened it in Ask
    p.step(Event::Shown);
    assert_eq!(p.mode, Mode::Find);
    assert_eq!(p.step(Event::Put { seq, result: Ok(()) }), vec![Effect::CloseSoon(seq)]);
    assert!(matches!(p.phase, Phase::Filed(_)));
}
