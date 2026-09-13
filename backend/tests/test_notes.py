import uuid

import pytest
from sqlalchemy import func, select

from app.core import notes, papers
from app.core.errors import InvalidInput, NotFound
from app.models import Note, Paper, Provenance

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
