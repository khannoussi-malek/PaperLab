from pathlib import Path

import pymupdf
import pytest

from app.core.manuscript_checks import pdf_layout as pl

BODY = "word " * 60  # wrapped by insert_textbox into a few lines, 60 words, all on the page


def make(path: Path, pages: list[dict]) -> Path:
    """pages: {"body": bool, "heading": str | None, "heading_y": float, "extra": str | None}"""
    doc = pymupdf.open()
    for spec in pages:
        page = doc.new_page(width=612, height=792)
        if spec.get("body"):
            page.insert_textbox(pymupdf.Rect(72, 60, 540, 300), BODY, fontsize=11)
        if spec.get("heading"):
            page.insert_text((72, spec.get("heading_y", 400)), spec["heading"], fontsize=11)
        if spec.get("extra"):
            page.insert_text((72, 500), spec["extra"], fontsize=11)
    doc.save(path)
    return path


def test_page_count_and_heading_mid_page(tmp_path):
    p = make(tmp_path / "a.pdf", [
        {"body": True}, {"body": True},
        {"body": True, "heading": "References"}, {"extra": "[1] A. Author"},
    ])
    s = pl.stats(p)
    assert (s.page_count, s.body_pages) == (4, 3)


def test_heading_that_starts_a_page_ends_the_body_the_page_before(tmp_path):
    p = make(tmp_path / "b.pdf", [
        {"body": True}, {"body": True}, {"heading": "7 REFERENCES", "heading_y": 100, "extra": "[1] A"},
    ])
    assert pl.stats(p).body_pages == 2


def test_no_heading(tmp_path):
    assert pl.stats(make(tmp_path / "c.pdf", [{"body": True}])) == pl.PdfStats(1, None)


def test_unresolved_marks_per_page(tmp_path):
    p = make(tmp_path / "d.pdf", [
        {"body": True}, {"extra": "see Figure ?? and Table ??"}, {"extra": "as shown in [?]"},
    ])
    assert pl.unresolved(p) == [(2, 2), (3, 1)]


def test_no_unresolved_marks(tmp_path):
    assert pl.unresolved(make(tmp_path / "e.pdf", [{"body": True}])) == []


def test_contents_page_references_line_does_not_end_the_body(tmp_path):
    p = make(tmp_path / "f.pdf", [
        {"body": True, "extra": "References"},  # contents page: a "References" line, body text above it
        {"body": True}, {"body": True},
        {"heading": "References", "heading_y": 100, "extra": "[1] A"},
    ])
    assert pl.stats(p).body_pages == 3


def test_running_head_references_on_bibliography_pages_do_not_move_the_body_end(tmp_path):
    # Body on pages 1-2; the real heading on page 3 has no body above it (body ends on page 2);
    # pages 4-5 repeat "References" as a running head in the top 10% band.
    p = make(tmp_path / "g.pdf", [
        {"body": True}, {"body": True},
        {"heading": "References", "heading_y": 400, "extra": "[1] A"},
        {"heading": "References", "heading_y": 30, "extra": "[2] B"},
        {"heading": "References", "heading_y": 30, "extra": "[3] C"},
    ])
    assert pl.stats(p).body_pages == 2


@pytest.mark.parametrize("words_above, expected_body", [(14, 1), (15, 2)])
def test_fresh_page_threshold_is_fifteen_words(tmp_path, words_above, expected_body):
    # Page 1 is body; page 2 has the heading with `words_above` words above it on the same page.
    p = make(tmp_path / f"h{words_above}.pdf", [
        {"body": True},
        {"heading": "References", "heading_y": 600, "extra": " ".join(["w"] * words_above)},
    ])
    assert pl.stats(p).body_pages == expected_body


def test_references_heading_in_the_top_band_of_a_letter_page_still_counts(tmp_path):
    # Heading at y0 ~ 51 on a letter page (inside the top 10%) with no body above it: a real heading, not a running head.
    p = make(tmp_path / "i.pdf", [
        {"body": True}, {"body": True},
        {"heading": "References", "heading_y": 60, "extra": "[1] A"},
    ])
    assert pl.stats(p).body_pages == 2


def test_single_running_head_after_a_mid_page_heading_does_not_beat_it(tmp_path):
    # Body on pages 1-2; a real heading mid-page on page 3 (outside the top band, no body above it);
    # page 4 carries one "References" running head at y0 ~ 30 and reference text, repeated nowhere else.
    p = make(tmp_path / "j.pdf", [
        {"body": True}, {"body": True},
        {"heading": "References", "heading_y": 300, "extra": "[1] A"},
        {"heading": "References", "heading_y": 30, "extra": "[2] B"},
    ])
    assert pl.stats(p).body_pages == 2
