import uuid

import pytest

from app.core import checks, prompts
from app.core.checks import CheckGuard, KeptLines, LineFilter, guard_for, parse_check, queries, take_turns, written_text
from app.core.retrieval import RetrievedChunk

GUARD = guard_for("the 32.4 BLEU score", ["pushing the GLUE score to new highs"])
DROPPED = "dropped"
WORDS25 = " ".join(["word"] * 25)

# (raw, kept verdict + cited, or DROPPED)
CASES = [
    ("Missing: the main result [C1]", ("missing", [1])),
    ("- Unsupported: the 32.4 BLEU score [C2]", ("unsupported", [2])),
    ("**Supported:** the dataset size [C1]", ("supported", [1])),
    ("missing: the baseline [C1]", ("missing", [1])),
    ("Unsupported: a claim the paper never makes", ("unsupported", [])),
    ("Missing: the main result", DROPPED),
    ("Supported: the method [C9]", DROPPED),
    ("Missing: the result [C1][C9]", ("missing", [1])),
    (f"Missing: {WORDS25} [C1]", ("missing", [1])),
    (f"Missing: {WORDS25} word [C1]", DROPPED),
    ("Missing: [C1]", DROPPED),
    ("Here is a better summary you could use.", DROPPED),
    ("Missing: rewrite it as “The model reaches a high score here today.” [C1]", DROPPED),
    ("Missing: the GLUE score of 80.5% [C1]", DROPPED),
    ("Unsupported: the score is 28.4, not 32.4 [C2]", DROPPED),
    ("Missing: pushing the GLUE score to new highs [C1]", DROPPED),
    ("Unsupported: the model is a CNN, not an LSTM [C2]", DROPPED),
    ("Unsupported: it is a CNN rather than an LSTM [C2]", DROPPED),
    ("Unsupported: the paper actually used a CNN [C2]", DROPPED),
    ("Unsupported: the paper in fact used a CNN [C2]", DROPPED),
    ("Unsupported: not supervised but unsupervised [C1]", DROPPED),
    ("Unsupported: the method is not merely supervised but unsupervised [C1]", DROPPED),
    ("Unsupported: it uses not only CNNs but LSTMs [C1]", DROPPED),
    ("Unsupported: the paper does not name the sample [C2]", ("unsupported", [2])),
    ("Unsupported: this is not supported by the passage [C2]", ("unsupported", [2])),
    ("Unsupported: Category: a survey of translation models [C1]", ("unsupported", [1])),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_line_table(raw, expected):
    reply = parse_check(raw, 3, GUARD)
    if expected == DROPPED:
        assert (reply.lines, reply.dropped) == ([], 1)
    else:
        assert [(line.verdict, line.cited) for line in reply.lines] == [expected]
        assert reply.dropped == 0


def test_blank_and_repeat_are_skipped_uncounted():
    reply = parse_check("\nSupported: the method [C1]\n   \nSupported: the method [C1]", 3, GUARD)
    assert (len(reply.lines), reply.dropped) == (1, 0)


def test_text_keeps_its_markers_and_cited_has_no_repeats():
    line = parse_check("Missing: a [C2] b [C1][C2][C9]", 3, GUARD).lines[0]
    assert line.text == "a [C2] b [C1][C2][C9]"
    assert line.cited == [2, 1]


def test_stable_grouping():
    raw = "Supported: a [C1]\nMissing: b [C1]\nUnsupported: c\nMissing: d [C2]"
    got = [line.text for line in parse_check(raw, 3, GUARD).lines]
    assert got == ["b [C1]", "d [C2]", "c", "a [C1]"]


def test_thirteen_lines_keep_twelve_and_count_one():
    raw = "\n".join(f"Missing: topic {chr(97 + i)} [C1]" for i in range(13))
    reply = parse_check(raw, 3, GUARD)
    assert (len(reply.lines), reply.dropped) == (12, 1)


def test_a_reader_quoting_the_paper_is_not_copying():
    guard = guard_for("pushing the GLUE score to new highs", ["pushing the GLUE score to new highs"])
    assert guard.copied == frozenset()
    assert parse_check("Supported: pushing the GLUE score to new highs [C1]", 3, guard).dropped == 0


def test_numbers_drop_thousands_separators():
    assert guard_for("we had 1,200 users in 2019, ok", []).numbers == frozenset({"1200", "2019"})


def test_the_prompt_splits_and_a_missing_part_raises(monkeypatch):
    assert sorted(checks.TASKS) == sorted(checks.EXIT_TESTS)
    assert "{task}" in checks.PROMPT_TEMPLATE and checks.SYSTEM_PROMPT.startswith("You check")
    text = prompts.load("check", 1).replace("<!-- summary -->", "<!-- other -->")
    monkeypatch.setattr(prompts, "load", lambda name, version: text)
    with pytest.raises(RuntimeError):
        checks._load(1)


def test_written_text_of_headings_only_is_empty():
    body = "Category:\nContext:  \nCorrectness:\nContributions:\nClarity:"
    assert written_text("five_cs", body) == ""
    assert written_text("five_cs", "CATEGORY: an empirical study\nclarity: fine") == "an empirical study\nfine"
    assert written_text("summary", "  Some text.  ") == "Some text."


def test_queries():
    five = "Category: an empirical study\nContext:\nCorrectness: sound\nContributions:\nClarity: ok"
    assert queries("five_cs", five) == ["an empirical study", "sound", "ok"]
    summary = "It trains a model. Short one! Then it tests the model on data.\nAnd a last line here."
    assert queries("summary", summary) == [
        "It trains a model.",
        "Then it tests the model on data.",
        "And a last line here.",
    ]
    many = " ".join(f"This is sentence number {i}." for i in range(20))
    assert len(queries("summary", many)) == 12
    assert queries("reconstruction", "Too short.") == ["Too short."]


def _chunk(text="x" * 10):
    return RetrievedChunk(id=uuid.uuid4(), paper_id=uuid.uuid4(), page=1, section=None, bbox=[], text=text)


def test_take_turns():
    a1, a2, b1, b2, c = (_chunk() for _ in range(5))
    assert take_turns([[a1, a2], [b1, b2]], 1000) == [a1, b1, a2, b2]
    assert take_turns([[a1, a2], [a1, b1]], 1000) == [a1, a2, b1]  # no repeats
    assert take_turns([[a1, a2], [b1]], 20) == [a1, b1]  # budget
    big, small = _chunk("y" * 50), _chunk("z" * 5)
    assert take_turns([[big, small]], 20) == [small]  # a chunk that doesn't fit is skipped, not split
    assert take_turns([[a1, a2], [b1]], 1000, taken=[a1.id]) == [b1, a2]


class _Llm:
    model, connection_name, host = "m", "c", "h"

    def __init__(self, tokens):
        self.tokens = tokens

    async def stream(self, system, prompt):
        for token in self.tokens:
            yield token


@pytest.mark.anyio
async def test_kept_lines_streams_only_kept_lines():
    tokens = ["Missing: the result [C", "1]\nHere is a better", " summary you could use.\nSupported: x [C1]"]
    kept = KeptLines(_Llm(tokens), 3, CheckGuard(frozenset(), frozenset()))
    assert (kept.model, kept.connection_name, kept.host) == ("m", "c", "h")
    got = [t async for t in kept.stream("s", "p")]
    assert got == ["Missing: the result [C1]\n", "Supported: x [C1]\n"]
    assert kept.raw == "".join(tokens)


def test_line_filter_counts():
    f = LineFilter(3, GUARD)
    assert f.feed("nonsense") is None and f.feed("") is None
    assert f.feed("Missing: the result [C1]") is not None
    assert (len(f.lines), f.dropped) == (1, 1)


def test_a_leading_heading_keeps_its_text():
    line = parse_check("Unsupported: Category: a survey of translation models [C1]", 3, GUARD).lines[0]
    assert line.text == "Category: a survey of translation models [C1]"


def test_numbers_are_read_strictly():
    g = guard_for("85 then 5 and 80", [])
    for bad in ("an accuracy of .85", "a share of 80,5 percent"):
        assert parse_check(f"Missing: {bad} [C1]", 3, g).dropped == 1
    assert parse_check("Missing: 85 and 5 and 80 [C1]", 3, g).dropped == 0
