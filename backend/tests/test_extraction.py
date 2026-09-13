import pytest

from app.core.errors import InvalidInput
from app.providers.extraction import extract


def test_blocks_have_one_based_pages_and_top_left_bboxes(sample_pdf):
    doc = extract(sample_pdf)

    assert doc.page_count == 2
    assert sorted({b.page for b in doc.blocks}) == [1, 2]
    title = doc.blocks[0]
    x0, y0, x1, y1 = title.bbox
    # Text inserted near the top of an A4/Letter page: small y in a top-left origin.
    assert x0 < x1 and y0 < y1 < 100


def test_detects_bold_and_size(sample_pdf):
    blocks = {b.text: b for b in extract(sample_pdf).blocks}

    assert blocks["Deep Paper Title"].bold and blocks["Deep Paper Title"].size == 18
    assert blocks["2 Method"].bold
    body = next(b for b in blocks.values() if b.text.startswith("The quick brown fox"))
    assert not body.bold and body.size == 11


def test_drops_rotated_margin_text(sample_pdf):
    assert not any("arXiv" in b.text for b in extract(sample_pdf).blocks)


def test_title_falls_back_to_largest_first_page_block(sample_pdf):
    assert extract(sample_pdf).title == "Deep Paper Title"


def test_metadata_title_wins_over_font_heuristic(titled_pdf):
    assert extract(titled_pdf).title == "Title From Metadata"


def test_pdf_without_text_layer_fails_loudly(blank_pdf):
    with pytest.raises(InvalidInput, match="no usable text layer"):
        extract(blank_pdf)
