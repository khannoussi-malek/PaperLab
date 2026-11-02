import uuid

import pytest

from app.core import notes
from app.core.errors import InvalidInput, NotFound
from app.models import Paper

pytestmark = pytest.mark.anyio

REGION = (60.0, 150.0, 420.0, 310.0)
FAR = (60.0, 500.0, 420.0, 600.0)


async def make_paper(session, path, page_count=1) -> Paper:
    paper = Paper(title="figure paper", file_path=None if path is None else str(path), page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


async def test_a_figure_note_quotes_the_caption_and_keeps_the_box(session, figure_pdf):
    paper = await make_paper(session, figure_pdf)

    note = await notes.create_figure_note(session, paper.id, 1, REGION, "see this")

    assert note.anchors[0].quoted_text == "Figure 1: A test figure."
    assert note.anchors[0].bbox == [REGION]
    assert (note.kind, note.provenance) == ("figure", "human")


async def test_no_caption_falls_back(session, figure_pdf):
    paper = await make_paper(session, figure_pdf)

    note = await notes.create_figure_note(session, paper.id, 1, FAR, "")

    assert note.anchors[0].quoted_text == "Figure on p. 1"


async def test_no_file_on_this_machine_falls_back(session, tmp_path):
    paper = await make_paper(session, tmp_path / "gone.pdf")

    note = await notes.create_figure_note(session, paper.id, 1, REGION, "")

    assert note.anchors[0].quoted_text == "Figure on p. 1"


async def test_a_page_out_of_range_is_invalid(session, figure_pdf):
    paper = await make_paper(session, figure_pdf)
    with pytest.raises(InvalidInput):
        await notes.create_figure_note(session, paper.id, 2, REGION, "")


async def test_a_bad_region_is_invalid(session, figure_pdf):
    paper = await make_paper(session, figure_pdf)
    with pytest.raises(InvalidInput):
        await notes.create_figure_note(session, paper.id, 1, (420.0, 150.0, 60.0, 310.0), "")
    with pytest.raises(NotFound):
        await notes.create_figure_note(session, uuid.uuid4(), 1, REGION, "")


async def test_a_paper_without_a_pdf_is_no_pdf(session):
    paper = await make_paper(session, None)
    with pytest.raises(InvalidInput, match="no_pdf"):
        await notes.create_figure_note(session, paper.id, 1, REGION, "")
