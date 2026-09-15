import pytest

from app.core.numbers import NumberCandidate, find_numbers, parse_number


@pytest.mark.parametrize(
    ("raw", "value", "error"),
    [
        ("88.5", 88.5, None),
        ("−3", -3.0, None),  # U+2212, the minus sign typeset papers use
        ("-3", -3.0, None),
        ("1,234", 1234.0, None),
        ("88.5 ± 0.3", 88.5, 0.3),
        ("88.5±0.3", 88.5, 0.3),
        ("34%", 34.0, None),
        ("110M", 110_000_000.0, None),
        ("1.2B", 1_200_000_000.0, None),
        ("340K", 340_000.0, None),
        ("1.2e-3", 0.0012, None),
        ("90.9*", 90.9, None),
        ("90.9†", 90.9, None),
        ("**90.9**", 90.9, None),
        ("  4.92\n", 4.92, None),
        (".5", 0.5, None),
    ],
)
def test_numbers_parse_to_value_and_error(raw, value, error):
    parsed = parse_number(raw)
    assert parsed.value == pytest.approx(value)
    assert parsed.error == (None if error is None else pytest.approx(error))


LABELS = ["", "   ", "—", "–", "-", "n/a", "N/A", "BERT-L", "(A)", "×106", "88.5 F1", "1,5", "±0.3"]


@pytest.mark.parametrize("raw", LABELS)
def test_labels_and_empty_cells_have_no_value(raw):
    parsed = parse_number(raw)
    assert (parsed.value, parsed.error) == (None, None)


def test_every_number_in_a_selection_is_a_candidate_with_the_word_after_it_as_unit():
    text = "BERT-L reaches 90.9 F1 on SQuAD 1.1 and 88.5 ± 0.3 EM, up 34% with 340M parameters."
    assert find_numbers(text) == [
        NumberCandidate(raw="90.9", value=90.9, error=None, unit_hint="F1"),
        NumberCandidate(raw="1.1", value=1.1, error=None, unit_hint=None),  # "and" is not a unit
        NumberCandidate(raw="88.5 ± 0.3", value=88.5, error=0.3, unit_hint="EM"),
        NumberCandidate(raw="34%", value=34.0, error=None, unit_hint="%"),
        NumberCandidate(raw="340M", value=340_000_000.0, error=None, unit_hint="parameters"),
    ]


def test_digits_inside_words_are_not_candidates():
    assert find_numbers("GPT-2 and v2 of word2vec, 3x faster") == []
