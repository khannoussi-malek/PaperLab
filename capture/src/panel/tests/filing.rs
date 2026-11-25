//! Find, ⌘↵ on a paper: put it in a workspace.

use super::*;
use crate::api::Workspace;

fn workspace(id: &str, name: &str) -> Workspace {
    Workspace { id: id.into(), name: name.into(), paper_count: 2 }
}

fn filing_graph_attention() -> Panel {
    let mut p = shown_with_library();
    typed(&mut p, "graph");
    assert_eq!(p.step(Event::SubmitAlt), vec![Effect::FetchWorkspaces]);
    p.step(Event::Workspaces(Ok(vec![workspace("w1", "Thesis"), workspace("w2", "Reading group")])));
    p
}

#[test]
fn command_enter_on_a_paper_lists_workspaces_typing_narrows_and_enter_puts_it_there() {
    let mut p = filing_graph_attention();
    assert!(matches!(&p.phase, Phase::Filing(f) if f.paper_id == "b" && f.title == "Graph attention networks"));
    assert_eq!(p.query, "", "the field now narrows the workspaces");
    assert_eq!(p.rows(), vec![Row::Workspace(0), Row::Workspace(1)]);
    p.step(Event::Query("read".into()));
    assert_eq!(p.rows(), vec![Row::Workspace(1)]);
    let seq = match p.step(Event::Submit).as_slice() {
        [Effect::PutInWorkspace { seq, workspace_id, paper_id }] if workspace_id == "w2" && paper_id == "b" => *seq,
        other => panic!("{other:?}"),
    };
    assert_eq!(p.step(Event::Submit), vec![], "Enter again waits for the answer");
    let done = p.step(Event::Put { seq, workspace_id: "w2".into(), result: Ok(()) });
    assert_eq!(done, vec![Effect::CloseSoon(seq)]);
    assert_eq!(p.phase, Phase::Filed("Put “Graph attention networks” in “Reading group”.".into()));
    assert_eq!(p.step(Event::CloseNow(seq)), vec![Effect::Close]);
    assert_eq!(p.last_workspace.as_deref(), Some("w2"), "first in the list next time, in Ask too");
}

#[test]
fn a_refused_put_stays_with_why_and_a_stray_answer_changes_nothing() {
    let mut p = filing_graph_attention();
    let Some(Effect::PutInWorkspace { seq, .. }) = p.step(Event::Submit).pop() else { panic!() };
    assert_eq!(p.step(Event::Put { seq: seq + 1, workspace_id: "w1".into(), result: Ok(()) }), vec![]);
    p.step(Event::Put { seq, workspace_id: "w1".into(), result: Err(ApiError::Said("w1 not found".into())) });
    assert!(matches!(&p.phase, Phase::Filing(f) if f.error.as_deref() == Some("w1 not found") && f.putting.is_none()));
    assert!(matches!(p.step(Event::Submit).as_slice(), [Effect::PutInWorkspace { .. }]), "try again");
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
    assert!(matches!(&p.phase, Phase::Filing(f) if f.paper_id == "n"));
}

#[test]
fn no_workspace_yet_or_offline_offers_paperlab() {
    let mut p = shown_with_library();
    typed(&mut p, "graph");
    p.step(Event::SubmitAlt);
    p.step(Event::Workspaces(Ok(vec![])));
    assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
    assert_eq!(p.step(Event::Submit), vec![Effect::OpenPaperLab, Effect::Close]);
}

#[test]
fn a_put_under_way_holds_through_tab_and_a_reopen_and_its_answer_lands() {
    let mut p = filing_graph_attention();
    let Some(Effect::PutInWorkspace { seq, .. }) = p.step(Event::Submit).pop() else { panic!() };
    assert_eq!(p.step(Event::NextMode { forward: true }), vec![], "Tab waits for the put");
    p.step(Event::Closed);
    p.mode = Mode::Ask; // a bubble reopened it in Ask
    p.step(Event::Shown);
    assert_eq!(p.mode, Mode::Find);
    assert_eq!(p.step(Event::Put { seq, workspace_id: "w1".into(), result: Ok(()) }), vec![Effect::CloseSoon(seq)]);
    assert!(matches!(p.phase, Phase::Filed(_)));
}
