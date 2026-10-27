from pathlib import Path

import pytest

from app.core import synctex

FIXTURE = Path(__file__).parent / "fixtures" / "synctex" / "main.synctex.gz"
ROOT = "/private/var/folders/38/hhp3h54n0cl3jkzlhbb7bn080000gp/T/tmp.UdqPSy8TCu"
BODY = "sections/body.tex"


@pytest.fixture(scope="module")
def idx():
    return synctex.index(FIXTURE.read_bytes(), ROOT)


def test_inputs_are_relative_and_bundle_files_are_dropped(idx):
    assert idx["inputs"] == ["main.tex", BODY]
    assert all(r[1] < 2 for r in idx["records"])
    assert {r[0] for r in idx["records"]} == {1, 2}


def test_another_root_keeps_nothing():
    other = synctex.index(FIXTURE.read_bytes(), "/elsewhere")
    assert other == {"inputs": [], "records": []}


def test_heading_on_page_two_and_later_lines_are_lower(idx):
    heading = synctex.forward(idx, BODY, 10)
    later = synctex.forward(idx, BODY, 14)
    assert heading["page"] == 2 and later["page"] == 2
    assert later["y"] > heading["y"]


def test_a_line_between_records_maps_to_the_next_record(idx):
    lines = sorted({r[2] for r in idx["records"] if r[1] == 1})
    gap = next(n for n in range(lines[0], lines[-1]) if n not in lines)
    after = min(n for n in lines if n > gap)
    assert synctex.forward(idx, BODY, gap) == synctex.forward(idx, BODY, after)


def test_past_the_end_uses_the_last_line_and_unknown_file_is_none(idx):
    assert synctex.forward(idx, BODY, 9999)["page"] == 2
    assert synctex.forward(idx, "nope.tex", 1) is None


@pytest.mark.parametrize("line", [3, 11, 14])
def test_inverse_round_trips(idx, line):
    p = synctex.forward(idx, BODY, line)
    assert synctex.inverse(idx, p["page"], p["x"], p["y"]) == {"file": BODY, "line": line}


def test_inverse_on_an_empty_page_is_none(idx):
    assert synctex.inverse(idx, 9, 10, 10) is None


SHORT = Path(__file__).parent / "fixtures" / "synctex_short" / "main.synctex.gz"
SHORT_ROOT = "/private/var/folders/38/hhp3h54n0cl3jkzlhbb7bn080000gp/T/tmp.hJsx4iunUW"


def test_a_click_at_the_left_edge_of_a_short_section_stays_in_that_section():
    idx = synctex.index(SHORT.read_bytes(), SHORT_ROOT)
    p = synctex.forward(idx, "sections/a.tex", 1)
    for dx in (0, 20):
        hit = synctex.inverse(idx, p["page"], p["x"] - dx, p["y"])
        assert hit == {"file": "sections/a.tex", "line": 1}


def test_an_index_without_kinds_counts_as_points_and_a_page_of_boxes_still_answers():
    old = {"inputs": ["a.tex"], "records": [[1, 0, 3, 72.0, 100.0]]}
    assert synctex.inverse(old, 1, 70, 100) == {"file": "a.tex", "line": 3}
    boxes = {"inputs": ["a.tex"], "records": [[1, 0, 4, 72.0, 100.0, "("]]}
    assert synctex.inverse(boxes, 1, 70, 100) == {"file": "a.tex", "line": 4}
