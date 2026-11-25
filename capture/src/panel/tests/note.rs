//! Note: find a paper, write on it, Enter saves; a note being written is never lost.

use super::*;

fn writing_on_graph_attention() -> Panel {
    let mut p = shown_with_library();
    p.step(Event::Mode(Mode::Note));
    typed(&mut p, "graph");
    assert_eq!(p.rows(), vec![Row::Paper(1)]);
    assert_eq!(p.step(Event::Submit), vec![]);
    p
}

fn saving(p: &mut Panel, note: &str) -> u64 {
    p.step(Event::Query(note.into()));
    match p.step(Event::Submit).as_slice() {
        [Effect::SaveNote { seq, paper_id, body }] => {
            assert_eq!((paper_id.as_str(), body.as_str()), ("b", note.trim()));
            *seq
        }
        other => panic!("{other:?}"),
    }
}

#[test]
fn enter_on_a_paper_empties_the_field_for_the_note_and_enter_saves_it_then_the_panel_closes() {
    let mut p = writing_on_graph_attention();
    assert!(matches!(&p.phase, Phase::Note(d) if d.paper_id == "b" && d.title == "Graph attention networks"));
    assert_eq!((p.query.as_str(), p.placeholder()), ("", "Write your note, then ↵"));
    assert_eq!(p.rows(), vec![], "while writing, Enter saves; there's nothing to pick");
    assert_eq!(p.step(Event::Submit), vec![], "an empty note isn't saved");
    let seq = saving(&mut p, "  Compare their attention heads with ours.  ");
    assert!(matches!(p.phase, Phase::SavingNote(_)));
    assert_eq!(p.step(Event::NoteSaved { seq, result: Ok(()) }), vec![Effect::CloseSoon(seq)]);
    assert_eq!(p.phase, Phase::NoteSaved("Saved on “Graph attention networks”.".into()));
    assert_eq!(p.step(Event::CloseNow(seq)), vec![Effect::Close]);
}

#[test]
fn a_save_that_fails_keeps_the_note_and_says_why() {
    let mut p = writing_on_graph_attention();
    let seq = saving(&mut p, "A thought");
    p.step(Event::NoteSaved { seq, result: Err(ApiError::Said("Paper b does not exist.".into())) });
    assert!(matches!(&p.phase, Phase::Note(d) if d.error.as_deref() == Some("Paper b does not exist.")));
    assert_eq!(p.query, "A thought", "not a word lost");
    let again = saving(&mut p, "A thought");
    p.step(Event::NoteSaved { seq: again, result: Err(ApiError::Unreachable) });
    assert!(matches!(&p.phase, Phase::Note(d) if d.error.as_deref() == Some(UNREACHABLE)));
    assert!(!p.reachable);
}

#[test]
fn a_note_being_written_survives_the_panel_closing_and_reopening_in_another_mode() {
    let mut p = writing_on_graph_attention();
    p.step(Event::Query("Half a tho".into()));
    p.step(Event::Closed);
    p.mode = Mode::Cite; // a bubble opened the panel in Cite
    p.step(Event::Shown);
    assert_eq!(p.mode, Mode::Note, "the note keeps its mode until it's saved or left");
    assert!(matches!(p.phase, Phase::Note(_)));
    assert_eq!(p.query, "Half a tho");
}

#[test]
fn a_late_or_stray_save_answer_changes_nothing() {
    let mut p = writing_on_graph_attention();
    let seq = saving(&mut p, "First");
    assert_eq!(p.step(Event::NoteSaved { seq: seq + 1, result: Ok(()) }), vec![]);
    assert!(matches!(p.phase, Phase::SavingNote(_)));
    p.step(Event::Mode(Mode::Find));
    assert_eq!(p.step(Event::NoteSaved { seq, result: Ok(()) }), vec![], "left Note: the answer has nowhere to go");
    assert_eq!(p.phase, Phase::Library);
}

#[test]
fn offline_with_no_papers_offers_to_open_paperlab() {
    let mut p = Panel::default();
    p.step(Event::Mode(Mode::Note));
    p.step(Event::Papers(Err(ApiError::Unreachable)));
    assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
    assert_eq!(p.step(Event::Submit), vec![Effect::OpenPaperLab, Effect::Close]);
}
