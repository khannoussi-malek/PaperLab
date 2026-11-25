//! Ask: workspaces, a streamed answer and what it offers once written.

use super::*;
use crate::api::{Said, Source, Workspace};

fn workspace(id: &str, name: &str) -> Workspace {
    Workspace { id: id.into(), name: name.into(), paper_count: 3 }
}

fn in_ask() -> Panel {
    let mut p = shown_with_library();
    assert_eq!(p.step(Event::Mode(Mode::Ask)), vec![Effect::FetchWorkspaces]);
    p.step(Event::Workspaces(Ok(vec![workspace("w1", "Thesis"), workspace("w2", "Reading group")])));
    p
}

fn asked(p: &mut Panel, question: &str) -> u64 {
    typed(p, question);
    match p.step(Event::Submit).as_slice() {
        [Effect::Ask { seq, .. }] => *seq,
        other => panic!("{other:?}"),
    }
}

#[test]
fn ask_lists_workspaces_and_enter_asks_the_picked_one() {
    let mut p = in_ask();
    assert_eq!(p.rows(), vec![Row::Workspace(0), Row::Workspace(1)]);
    assert_eq!(p.step(Event::Submit), vec![], "no question yet");
    typed(&mut p, "what is attention?");
    p.step(Event::Down);
    let seq = p.seq + 1;
    let ask = Effect::Ask { seq, workspace_id: "w2".into(), question: "what is attention?".into() };
    assert_eq!(p.step(Event::Submit), vec![ask]);
}

#[test]
fn the_answer_streams_in_and_then_offers_copy_open_and_its_papers() {
    let mut p = in_ask();
    let seq = asked(&mut p, "what is attention?");
    assert_eq!(p.rows(), vec![], "nothing to act on while it is written");
    let sources = vec![
        Source { label: "C1".into(), paper_id: "a".into(), page: 2 },
        Source { label: "C2".into(), paper_id: "b".into(), page: 5 },
        Source { label: "C3".into(), paper_id: "a".into(), page: 7 },
    ];
    p.step(Event::Heard { seq, result: Ok(Said::Sources(sources)) });
    p.step(Event::Heard { seq, result: Ok(Said::Token("Weights [C1]".into())) });
    p.step(Event::Heard { seq, result: Ok(Said::Token(" over tokens [C2].".into())) });
    p.step(Event::Heard { seq, result: Ok(Said::Done) });
    let Phase::Answer(a) = &p.phase else { panic!("{:?}", p.phase) };
    assert_eq!(a.text, "Weights [C1] over tokens [C2].");
    assert_eq!(a.cited().iter().map(|c| c.labels.join(",")).collect::<Vec<_>>(), vec!["C1,C3", "C2"]);
    assert_eq!(p.rows(), vec![Row::CopyAnswer, Row::OpenAnswer, Row::Source(0), Row::Source(1)]);
    p.step(Event::Down);
    assert_eq!(p.step(Event::Submit), vec![Effect::OpenWorkspace("w1".into()), Effect::Close]);
    p.step(Event::Up);
    let copy = p.step(Event::Submit);
    assert!(matches!(copy.as_slice(), [Effect::Copy { text, .. }] if text == "Weights [C1] over tokens [C2]."), "{copy:?}");
}

#[test]
fn the_workspace_asked_comes_first_next_time() {
    let mut p = in_ask();
    typed(&mut p, "q");
    p.step(Event::Down);
    p.step(Event::Submit);
    p.step(Event::Query(String::new()));
    assert_eq!(p.rows(), vec![Row::Workspace(1), Row::Workspace(0)]);
}

#[test]
fn an_answer_survives_closing_and_reopening_but_typing_leaves_it() {
    let mut p = in_ask();
    let seq = asked(&mut p, "what is attention?");
    p.step(Event::Closed);
    assert_eq!(p.step(Event::Shown), vec![Effect::FetchPapers, Effect::FetchWorkspaces]);
    p.step(Event::Heard { seq, result: Ok(Said::Token("Still coming.".into())) });
    assert!(matches!(&p.phase, Phase::Answer(a) if a.text == "Still coming."));
    assert_eq!(p.query, "what is attention?", "the question stays with its answer");
    p.step(Event::Query("another".into()));
    assert_eq!(p.step(Event::Heard { seq, result: Ok(Said::Token("late".into())) }), vec![]);
    assert_eq!(p.phase, Phase::Library);
}

#[test]
fn an_answer_that_fails_keeps_what_was_written_and_offline_offers_paperlab() {
    let mut p = in_ask();
    let seq = asked(&mut p, "q");
    p.step(Event::Heard { seq, result: Ok(Said::Token("Half".into())) });
    p.step(Event::Heard { seq, result: Ok(Said::Failed("The model stopped.".into())) });
    assert!(matches!(&p.phase, Phase::Answer(a) if a.text == "Half" && a.state == Writing::Failed("The model stopped.".into())));
    let mut off = in_ask();
    let seq = asked(&mut off, "q");
    off.step(Event::Heard { seq, result: Err(ApiError::Unreachable) });
    assert_eq!(off.rows(), vec![Row::OpenPaperLab]);
}

#[test]
fn no_workspace_yet_offers_to_open_paperlab() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Ask));
    p.step(Event::Workspaces(Ok(vec![])));
    assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
}

#[test]
fn a_second_question_does_not_get_the_first_answers_words() {
    let mut p = in_ask();
    let first = asked(&mut p, "first");
    let second = asked(&mut p, "second");
    p.step(Event::Heard { seq: first, result: Ok(Said::Token("old".into())) });
    p.step(Event::Heard { seq: second, result: Ok(Said::Token("new".into())) });
    assert!(matches!(&p.phase, Phase::Answer(a) if a.text == "new"), "{:?}", p.phase);
}

#[test]
fn a_copied_answer_comes_back_with_its_question_when_the_panel_reopens() {
    let mut p = in_ask();
    let seq = asked(&mut p, "what is attention?");
    p.step(Event::Heard { seq, result: Ok(Said::Token("Weights.".into())) });
    p.step(Event::Heard { seq, result: Ok(Said::Done) });
    let copy = p.step(Event::Submit);
    let [Effect::Copy { seq, .. }] = copy.as_slice() else { panic!("{copy:?}") };
    p.step(Event::Copied { seq: *seq, what: "the answer".into(), result: Ok(()) });
    p.step(Event::Closed);
    p.step(Event::Shown);
    assert!(matches!(&p.phase, Phase::Answer(a) if a.text == "Weights."), "{:?}", p.phase);
    assert_eq!(p.query, "what is attention?");
}

#[test]
fn a_workspace_list_error_stays_in_ask() {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Ask));
    p.step(Event::Workspaces(Err(ApiError::Said("Workspaces are being migrated.".into()))));
    assert_eq!(p.ask_error.as_deref(), Some("Workspaces are being migrated."));
    assert_eq!(p.library_error, None, "Find's line stays clear");
}
