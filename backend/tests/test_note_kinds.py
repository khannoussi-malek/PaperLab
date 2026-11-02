import pytest
from sqlalchemy.exc import IntegrityError
from test_note_papers import paper_only_note

from app.core import notes
from app.models import Note, Paper, Provenance

pytestmark = pytest.mark.anyio


async def test_the_constraint_refuses_bogus_and_null_is_fine(session):
    session.add(Note(body="ok", provenance="human", kind=None))
    session.add(Note(body="ok", provenance="human", kind="five_cs"))
    await session.commit()
    session.add(Note(body="bad", provenance="human", kind="bogus"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.parametrize("provenance", [Provenance.HUMAN, Provenance.LLM, Provenance.LLM_EDITED])
async def test_a_kind_on_each_provenance_leaves_it_alone(session, provenance):
    note = await paper_only_note(session, provenance=provenance)
    view = await notes.update_note(session, note.id, kind="summary")
    assert (view.kind, view.provenance) == ("summary", provenance)


async def test_clearing_a_kind_and_updated_at_moves_only_on_a_change(session):
    note = await paper_only_note(session)  # created at NOW, a fixed past date
    before = note.updated_at
    same = await notes.update_note(session, note.id, kind=notes.UNSET, color=note.color)
    assert same.updated_at == before
    set_ = await notes.update_note(session, note.id, kind="figure")
    assert (set_.kind, set_.updated_at > before) == ("figure", True)
    assert (await notes.update_note(session, note.id, kind="figure")).updated_at == set_.updated_at
    cleared = await notes.update_note(session, note.id, kind=None)
    assert cleared.kind is None
    assert (await notes.update_note(session, note.id, kind=None)).updated_at == cleared.updated_at


async def test_a_whole_paper_note_on_a_pdf_paper_is_linked_with_no_anchor_and_lists_first(session):
    paper = Paper(title="p", file_path="/x.pdf", page_count=2)
    session.add(paper)
    await session.commit()
    anchored = await notes.create_human_note(
        session, "a", notes.Anchor(paper.id, 1, [(1, 2, 3, 4)], "q")
    )
    whole = await notes.create_paper_note(session, paper.id, "w", kind="reconstruction")
    assert (whole.anchors, whole.paper_ids, whole.kind, whole.provenance) == ([], [paper.id], "reconstruction", "human")
    assert [n.id for n in await notes.list_notes_for_paper(session, paper.id)] == [whole.id, anchored.id]
