import re

import pytest

from app.core.finding_lines import clean_line, grams, reads_as_wording, split_label

REF = re.compile(r"\[C(\d+)\]")


@pytest.mark.parametrize(
    "raw",
    ["- Missing: x", "* Missing: x", "• Missing: x", "1. Missing: x", "1) Missing: x", "**Missing:** x"],
)
def test_clean_line_strips_list_and_emphasis(raw):
    assert clean_line(raw) == "Missing: x"


def test_split_label():
    assert split_label("MISSING: a gap") == ("missing", "a gap")
    assert split_label("Missing : a gap") == ("missing", "a gap")
    assert split_label("Supported: ok [C1]") == ("supported", "ok [C1]")
    assert split_label("Sure, here you go") is None


@pytest.mark.parametrize(
    "point",
    [
        "the “main result” is thin",
        "it should read better",
        "use this instead of that",
        "gap here: the main result is thin",
    ],
)
def test_reads_as_wording_true(point):
    assert reads_as_wording(point, REF, set())


def test_reads_as_wording_shared_gram():
    copied = grams(["we sampled forty users from three campuses"])
    assert reads_as_wording("we sampled forty users from three campuses", REF, copied)


def test_reads_as_wording_false():
    assert not reads_as_wording("the main result [C1]", REF, set())
    assert not reads_as_wording("the reader's claim", REF, set())
