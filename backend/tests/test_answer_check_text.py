from app.core.answer_check_text import answer_sentences


def test_marker_inside_and_after_punctuation():
    s = answer_sentences("It reached 28.4 BLEU [C2]. It used eight GPUs. [C3]\n\nNothing here.")
    assert [(x.text, x.labels) for x in s] == [
        ("It reached 28.4 BLEU.", ("C2",)),
        ("It used eight GPUs.", ("C3",)),
        ("Nothing here.", ()),
    ]
    assert [x.index for x in s] == [0, 1, 2]


def test_several_labels_dedup_in_order():
    assert answer_sentences("A and B [C3][C1][C3].")[0].labels == ("C3", "C1")


def test_list_items_and_table_rows_are_one_sentence_each():
    s = answer_sentences("- Dose 5 mg [C1]\n- Halve it at 80 [C2]\n\n| a | b [C3] |\n|---|---|\n| 1 | 2 [C4] |")
    assert [x.labels for x in s] == [("C1",), ("C2",), ("C3",), ("C4",)]


def test_headings_notes_blocks_and_note_citations_are_skipped():
    content = "## Dose\n\nUse 5 mg [C1] [N2].\n\n:::note\nA suggested note [C1].\n:::\n\nSee your note [N1]."
    s = answer_sentences(content)
    assert [(x.text, x.labels) for x in s] == [("Use 5 mg.", ("C1",)), ("See your note.", ())]


def test_decimal_and_abbreviation_do_not_split():
    assert len(answer_sentences("The HR was 0.69 (e.g. in ARISTOTLE) vs. warfarin [C1].")) == 1


def test_two_sentences_in_one_list_item_split():
    s = answer_sentences("1. It is 5 mg [C1]. Halve it at 80 [C2].")
    assert [(x.text, x.labels) for x in s] == [("It is 5 mg.", ("C1",)), ("Halve it at 80.", ("C2",))]


def test_empty_answer():
    assert answer_sentences("") == []
    assert answer_sentences("   \n\n") == []
