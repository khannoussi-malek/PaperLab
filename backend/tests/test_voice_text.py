import pytest

from app.core.voice_text import SentenceSplitter, heard_text, speakable


def chunks_of(tokens):
    splitter = SentenceSplitter()
    out = []
    for token in tokens:
        out.extend(splitter.feed(token))
    out.extend(splitter.flush())
    return out


def test_splits_whole_sentences_across_arbitrary_tokens():
    assert chunks_of(["Attention ", "wor", "ks. It ", "is fast."]) == ["Attention works.", "It is fast."]


@pytest.mark.parametrize(
    "text",
    [
        "Vaswani et al. report it.",
        "See Fig. 3 for it.",
        "It scored 28.4 overall.",
        "As in e.g. this one.",
        "Compare A vs. B now.",
    ],
)
def test_protected_forms_do_not_end_a_sentence(text):
    assert chunks_of([text]) == [text]


def test_marker_split_across_tokens_stays_with_its_sentence():
    assert chunks_of(["It works [C", "1]. Next one."]) == ["It works [C1].", "Next one."]


def test_first_chunk_may_end_at_a_clause_after_six_words_but_later_ones_may_not():
    text = "One two three four five six, seven eight. Nine ten eleven twelve thirteen fourteen, fifteen."
    assert chunks_of([text]) == [
        "One two three four five six,",
        "seven eight.",
        "Nine ten eleven twelve thirteen fourteen, fifteen.",
    ]


def test_text_without_an_ending_comes_out_on_flush():
    assert chunks_of(["No ending here"]) == ["No ending here"]


def test_speakable_strips_markers_markdown_and_spells_symbols():
    text = "**Vaswani** et al. found p < 0.05 in 95% of Fig. 2 [C2][N1]."
    assert speakable(text) == "Vaswani et al found p less than 0.05 in 95 percent of Figure 2."


def test_speakable_of_only_markers_is_empty():
    assert speakable(" [C1] [N2] ") == ""


def test_heard_text_keeps_whole_chunks_then_a_share_of_the_cut_one():
    chunks = [("One two.", 1.0), ("Three four five six.", 2.0)]
    assert heard_text(chunks, 0) == ""
    assert heard_text(chunks, 1.0) == "One two."
    assert heard_text(chunks, 2.0) == "One two. Three four"
    assert heard_text(chunks, 99) == "One two. Three four five six."
