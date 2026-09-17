import uuid
from pathlib import Path

import pytest
from pdf_papers import TWICE, TWO_LINE_QUOTE, TWO_PARAGRAPH_QUOTE, chunked_paper
from sqlalchemy import func, select

from app.core import notes, papers
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import LLMOutput, Note, Paper, Provenance, note_anchors

pytestmark = pytest.mark.anyio


async def make_paper(session, page_count=3, file_path="/nonexistent.pdf") -> Paper:
    paper = Paper(title="test paper", file_path=file_path, page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


def anchor(paper: Paper, page=1, top=400.0, quote="effective trans-\nfer learning") -> notes.Anchor:
    return notes.Anchor(paper_id=paper.id, page=page, bbox=[(72.0, top, 290.0, top + 10)], quoted_text=quote)


async def test_create_human_note_normalizes_body_and_quote(session):
    paper = await make_paper(session)

    note = await notes.create_human_note(session, "  worth citing ", anchor(paper))

    assert note.provenance == Provenance.HUMAN
    assert note.body == "worth citing"
    assert note.anchors == [notes.Anchor(paper.id, 1, [(72.0, 400.0, 290.0, 410.0)], "effective transfer learning")]


async def test_create_rejects_page_outside_paper(session):
    paper = await make_paper(session, page_count=3)
    with pytest.raises(InvalidInput):
        await notes.create_human_note(session, "", anchor(paper, page=4))


async def test_create_rejects_empty_bbox(session):
    paper = await make_paper(session)
    with pytest.raises(InvalidInput):
        await notes.create_human_note(session, "", notes.Anchor(paper.id, 1, [], "a quote"))


async def test_create_rejects_unknown_paper(session):
    never_saved = Paper(id=uuid.uuid4(), title="ghost", file_path="/ghost.pdf")
    with pytest.raises(NotFound):
        await notes.create_human_note(session, "", anchor(never_saved))


async def test_list_notes_in_reading_order(session):
    paper = await make_paper(session)
    page_two = await notes.create_human_note(session, "p2", anchor(paper, page=2, top=100))
    page_one_low = await notes.create_human_note(session, "p1 low", anchor(paper, page=1, top=500))
    page_one_high = await notes.create_human_note(session, "p1 high", anchor(paper, page=1, top=100))

    listed = await notes.list_notes_for_paper(session, paper.id)

    assert [n.id for n in listed] == [page_one_high.id, page_one_low.id, page_two.id]


async def test_editing_llm_note_flips_provenance_but_human_stays_human(session):
    paper = await make_paper(session)
    human = await notes.create_human_note(session, "mine", anchor(paper))
    llm_note = Note(body="model said", provenance=Provenance.LLM)
    session.add(llm_note)
    await session.commit()

    assert (await notes.update_note(session, human.id, body="still mine")).provenance == Provenance.HUMAN
    assert (await notes.update_note(session, llm_note.id, body="model said")).provenance == Provenance.LLM
    assert (await notes.update_note(session, llm_note.id, body="I rewrote it")).provenance == Provenance.LLM_EDITED


async def test_delete_note(session):
    paper = await make_paper(session)
    note = await notes.create_human_note(session, "", anchor(paper))

    await notes.delete_note(session, note.id)

    assert await notes.list_notes_for_paper(session, paper.id) == []
    with pytest.raises(NotFound):
        await notes.delete_note(session, note.id)


async def test_deleting_paper_removes_file_and_anchors_but_keeps_notes(session, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    paper = await make_paper(session, page_count=1, file_path=str(pdf))
    note = await notes.create_human_note(session, "keep me", anchor(paper))

    await papers.delete_paper(session, paper.id)

    assert not pdf.exists()
    assert await session.scalar(select(func.count()).select_from(Note).where(Note.id == note.id)) == 1
    with pytest.raises(NotFound):
        await notes.list_notes_for_paper(session, paper.id)


# --- MCP notes: placing a quote (Q1) ---------------------------------------------------------------------------------

# What the client's model reads when a quote can't be placed.
NOT_FOUND_HINT = "Copy quoted_text exactly from one passage of this paper, as search_library returned it."
AMBIGUOUS_HINT = "This text appears more than once in the paper. Quote a longer stretch around it."


def inside(rect, block, slack=0.5) -> bool:
    return block[0] - slack <= rect[0] and rect[2] <= block[2] + slack and block[1] - slack <= rect[1] <= block[3]


def test_fold_makes_quotes_dashes_ligatures_spacing_and_case_plain():
    assert notes.fold(" The “ﬁrst”\n top–left re­trieval — It’s ") == (
        'the "first" top-left retrieval - it\'s'
    )


async def test_a_quote_is_placed_on_its_lines_when_the_pdf_is_here(session, tmp_path):
    paper, chunks, _ = await chunked_paper(session, tmp_path)
    narrow = chunks[0].bbox[1]  # page 1's second paragraph

    anchor = await notes.locate_quote(session, paper.id, TWO_LINE_QUOTE)

    assert (anchor.paper_id, anchor.page, anchor.quoted_text) == (paper.id, 1, TWO_LINE_QUOTE)
    assert len(anchor.bbox) == 2 and all(inside(rect, narrow) for rect in anchor.bbox)  # not the caption below
    assert anchor.bbox[0][0] > narrow[0] + 50  # starts mid-line: the quoted words, not the whole paragraph


async def test_without_the_pdf_a_quote_is_placed_on_its_paragraph(session, tmp_path):
    paper, chunks, _ = await chunked_paper(session, tmp_path)
    Path(paper.file_path).unlink()

    anchor = await notes.locate_quote(session, paper.id, TWO_LINE_QUOTE)

    assert anchor.bbox == [tuple(chunks[0].bbox[1])]


async def test_case_and_line_breaks_do_not_matter(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path)
    shouted = "  THE MODEL cites each passage\nit uses, and the reader CAN check every claim "

    anchor = await notes.locate_quote(session, paper.id, shouted)

    assert (anchor.page, len(anchor.bbox)) == (1, 2)
    assert anchor.quoted_text == "THE MODEL cites each passage it uses, and the reader CAN check every claim"


async def test_typographic_dashes_still_find_the_passage(session, tmp_path):
    paper, chunks, _ = await chunked_paper(session, tmp_path)

    anchor = await notes.locate_quote(session, paper.id, "stored in PDF points with a top–left origin")

    assert anchor.page == 2
    # PyMuPDF can't match the en dash against the page's hyphen, so the paragraph stands in for the lines.
    assert anchor.bbox == [tuple(chunks[1].bbox[0])]


async def test_a_quote_across_two_paragraphs_of_one_chunk_covers_both(session, tmp_path):
    paper, chunks, _ = await chunked_paper(session, tmp_path)
    wide, narrow = chunks[0].bbox

    with_pdf = await notes.locate_quote(session, paper.id, TWO_PARAGRAPH_QUOTE)
    Path(paper.file_path).unlink()
    without_pdf = await notes.locate_quote(session, paper.id, TWO_PARAGRAPH_QUOTE)

    assert len(with_pdf.bbox) == 2  # not the caption between the paragraphs that repeats the words
    assert inside(with_pdf.bbox[0], wide) and inside(with_pdf.bbox[1], narrow)
    assert without_pdf.bbox == [tuple(wide), tuple(narrow)]


@pytest.mark.parametrize(
    ("quote", "code", "details"),
    [
        ("A sentence this paper never says.", "quote_not_found", {"hint": NOT_FOUND_HINT}),
        (TWICE, "quote_ambiguous", {"pages": [1], "hint": AMBIGUOUS_HINT}),
        (" \n ", "empty_quote", {}),
    ],
)
async def test_a_quote_that_cannot_be_placed_is_refused(session, tmp_path, quote, code, details):
    paper, _, _ = await chunked_paper(session, tmp_path)

    with pytest.raises(InvalidInput, match=f"^{code}$") as refused:
        await notes.locate_quote(session, paper.id, quote)

    assert refused.value.details == details


async def test_placing_a_quote_needs_a_known_paper_with_chunks(session):
    with pytest.raises(NotFound):
        await notes.locate_quote(session, uuid.uuid4(), "anything")
    unchunked = await make_paper(session)
    with pytest.raises(Conflict, match="^paper_not_ready$"):
        await notes.locate_quote(session, unchunked.id, "anything")


async def test_an_mcp_note_is_an_llm_note_whose_output_keeps_the_original_words(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path)

    note = await notes.create_llm_note(session, paper.id, "  Grounding makes answers checkable. ", TWO_LINE_QUOTE)

    located = await notes.locate_quote(session, paper.id, TWO_LINE_QUOTE)
    assert (note.body, note.provenance, note.color) == ("Grounding makes answers checkable.", "llm", "#facc15")
    assert note.anchors == [located]
    output = await session.get(LLMOutput, note.source_id)
    assert (output.kind, output.paper_id, output.content, output.model, output.prompt_version) == (
        "mcp", paper.id, "Grounding makes answers checkable.", "mcp", 0
    )
    chunk_ids = await session.scalars(select(note_anchors.c.chunk_id).where(note_anchors.c.note_id == note.id))
    assert list(chunk_ids) == [None]  # D10

    edited = await notes.update_note(session, note.id, body="In my words: answers can be checked.")

    assert edited.provenance == Provenance.LLM_EDITED
    await session.refresh(output)
    assert output.content == "Grounding makes answers checkable."


async def test_an_mcp_note_needs_a_body_and_a_placeable_quote(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path)

    with pytest.raises(InvalidInput, match="^empty_body$"):
        await notes.create_llm_note(session, paper.id, "  ", TWO_LINE_QUOTE)
    with pytest.raises(InvalidInput, match="^quote_not_found$"):
        await notes.create_llm_note(session, paper.id, "a note", "not in this paper")
    assert await session.scalar(select(func.count()).select_from(LLMOutput).where(LLMOutput.paper_id == paper.id)) == 0
