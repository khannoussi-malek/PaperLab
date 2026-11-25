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
fn a_note_waits_aside_when_the_panel_reopens_elsewhere_and_a_copied_doi_does_not_touch_it() {
    let mut p = writing_on_graph_attention();
    p.step(Event::Query("Half a tho".into()));
    p.step(Event::Closed);
    p.mode = Mode::Find; // the copied-DOI bubble opens Find…
    p.step(Event::Shown);
    p.step(Event::Query("10.48550/arXiv.1706.03762".into())); // …with the DOI typed in
    assert_eq!((p.mode, p.query.as_str()), (Mode::Find, "10.48550/arXiv.1706.03762"));
    p.step(Event::Closed);
    p.mode = Mode::Note;
    p.step(Event::Shown);
    assert!(matches!(&p.phase, Phase::Note(d) if d.paper_id == "b"));
    assert_eq!(p.query, "Half a tho", "not a word lost, none added");
}

#[test]
fn tab_away_and_back_or_a_drop_keeps_the_note() {
    let mut p = writing_on_graph_attention();
    p.step(Event::Query("Compare heads".into()));
    p.step(Event::NextMode { forward: true });
    assert_eq!((p.mode, p.query.as_str(), &p.phase), (Mode::Novelty, "", &Phase::Library), "the next mode gets a clean field");
    p.step(Event::Mode(Mode::Note));
    assert!(matches!(p.phase, Phase::Note(_)));
    assert_eq!(p.query, "Compare heads");
    p.step(Event::DropRefused);
    assert_eq!(p.mode, Mode::Find);
    p.step(Event::Mode(Mode::Note));
    assert!(matches!(&p.phase, Phase::Note(d) if d.paper_id == "b"), "a drop sets the note aside too");
    assert_eq!((p.query.as_str(), p.mode), ("Compare heads", Mode::Note));
}

#[test]
fn a_save_answer_reaches_a_note_set_aside() {
    let mut p = writing_on_graph_attention();
    let seq = saving(&mut p, "First");
    p.step(Event::Mode(Mode::Cite));
    assert_eq!(p.step(Event::NoteSaved { seq, result: Err(ApiError::Said("Busy.".into())) }), vec![]);
    assert_eq!(p.phase, Phase::Library, "Cite stays Cite");
    p.step(Event::Mode(Mode::Note));
    assert!(matches!(&p.phase, Phase::Note(d) if d.error.as_deref() == Some("Busy.")), "back with why");
    let again = saving(&mut p, "First");
    p.step(Event::Mode(Mode::Find));
    p.step(Event::NoteSaved { seq: again, result: Ok(()) });
    p.step(Event::Mode(Mode::Note));
    assert_eq!((&p.phase, p.query.as_str()), (&Phase::Library, ""), "saved while aside: nothing left to bring back");
}

#[test]
fn enter_on_an_empty_or_too_long_note_says_why_and_an_edit_clears_it() {
    let mut p = writing_on_graph_attention();
    assert_eq!(p.step(Event::Submit), vec![]);
    assert!(matches!(&p.phase, Phase::Note(d) if d.error.as_deref() == Some("Type the note first, then ↵ saves it.")));
    p.step(Event::Query("x".repeat(50_001)));
    assert_eq!(p.step(Event::Submit), vec![]);
    assert!(matches!(&p.phase, Phase::Note(d) if d.error.as_ref().is_some_and(|e| e.contains("50000"))));
    p.step(Event::Query("short".into()));
    assert!(matches!(&p.phase, Phase::Note(d) if d.error.is_none()));
}

#[test]
fn a_saved_note_leaves_the_field_and_a_stray_answer_changes_nothing() {
    let mut p = writing_on_graph_attention();
    let seq = saving(&mut p, "First");
    assert_eq!(p.step(Event::NoteSaved { seq: seq + 1, result: Ok(()) }), vec![]);
    assert!(matches!(p.phase, Phase::SavingNote(_)));
    p.step(Event::NoteSaved { seq, result: Ok(()) });
    assert_eq!(p.query, "", "the saved text leaves the field");
}

#[test]
fn offline_with_no_papers_offers_to_open_paperlab() {
    let mut p = Panel::default();
    p.step(Event::Mode(Mode::Note));
    p.step(Event::Papers(Err(ApiError::Unreachable)));
    assert_eq!(p.rows(), vec![Row::OpenPaperLab]);
    assert_eq!(p.step(Event::Submit), vec![Effect::OpenPaperLab, Effect::Close]);
}
