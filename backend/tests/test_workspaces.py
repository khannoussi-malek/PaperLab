import uuid

import pytest
from sqlalchemy import func, insert, select, text, update

from app.core import notes, workspaces
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Note, Paper, Provenance, note_anchors, workspace_papers

pytestmark = pytest.mark.anyio

# Tests share the dev database, where the owner's own workspaces are visible: names carry a per-run suffix.
RUN = uuid.uuid4().hex[:8]


async def make_paper(session, title="A paper", age_days=0) -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", page_count=5)
    session.add(paper)
    await session.commit()
    # The test transaction freezes now(); age papers explicitly to order them.
    await session.execute(
        update(Paper).where(Paper.id == paper.id).values(created_at=text(f"now() - interval '{age_days} days'"))
    )
    return paper


async def note_on(session, paper: Paper, page=1, top=100.0, body="a note") -> notes.NoteView:
    anchor = notes.Anchor(paper_id=paper.id, page=page, bbox=[(72.0, top, 290.0, top + 10)], quoted_text="a quote")
    return await notes.create_human_note(session, body, anchor)


async def test_create_strips_the_name_and_lists_alphabetically_with_counts(session):
    thesis = await workspaces.create(session, f"  Thesis ch.2 {RUN} ")
    alpha = await workspaces.create(session, f"Alpha review {RUN}")
    first, second = await make_paper(session, "First"), await make_paper(session, "Second")
    for paper in (first, second):
        await workspaces.add_paper(session, thesis.id, paper.id)
    await note_on(session, first)
    await note_on(session, second)
    both = await note_on(session, first, page=2)
    # One note anchored on two workspace papers counts once.
    await session.execute(
        insert(note_anchors).values(note_id=both.id, paper_id=second.id, page=3, bbox=[[1, 2, 3, 4]], quoted_text="q")
    )

    ordered = await workspaces.list_workspaces(session)
    listed = {w.id: w for w in ordered}

    assert (thesis.name, thesis.paper_count, thesis.note_count) == (f"Thesis ch.2 {RUN}", 0, 0)
    assert (listed[thesis.id].paper_count, listed[thesis.id].note_count) == (2, 3)
    assert (listed[alpha.id].paper_count, listed[alpha.id].note_count) == (0, 0)
    assert [w.id for w in ordered].index(alpha.id) < [w.id for w in ordered].index(thesis.id)  # by name
    assert (await workspaces.get(session, thesis.id)).note_count == 3


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
async def test_a_name_needs_1_to_80_characters(session, name):
    with pytest.raises(InvalidInput, match="1 to 80 characters"):
        await workspaces.create(session, name)
    workspace = await workspaces.create(session, RUN + "x" * 72)  # 80 characters
    with pytest.raises(InvalidInput, match="1 to 80 characters"):
        await workspaces.rename(session, workspace.id, name)


async def test_a_duplicate_name_conflicts_on_create_and_on_rename(session):
    first = await workspaces.create(session, f"Thesis {RUN}")
    second = await workspaces.create(session, f"Review {RUN}")

    with pytest.raises(Conflict, match="^workspace_name_taken$"):
        await workspaces.create(session, f" Thesis {RUN} ")
    with pytest.raises(Conflict, match="^workspace_name_taken$"):
        await workspaces.rename(session, second.id, f"Thesis {RUN}")
    assert (await workspaces.rename(session, first.id, f"Thesis {RUN}")).name == f"Thesis {RUN}"
    assert (await workspaces.rename(session, second.id, f"Survey {RUN}")).name == f"Survey {RUN}"


async def test_unknown_workspace_or_paper_is_not_found(session):
    workspace = await workspaces.create(session, f"Thesis {RUN}")
    paper = await make_paper(session)
    missing = uuid.uuid4()

    for call in [
        workspaces.get(session, missing),
        workspaces.rename(session, missing, f"New {RUN}"),
        workspaces.delete(session, missing),
        workspaces.add_paper(session, missing, paper.id),
        workspaces.remove_paper(session, missing, paper.id),
        workspaces.papers(session, missing),
        workspaces.notes(session, missing),
    ]:
        with pytest.raises(NotFound, match=f"^workspace {missing} not found$"):
            await call
    with pytest.raises(NotFound, match=f"^paper {missing} not found$"):
        await workspaces.add_paper(session, workspace.id, missing)
    with pytest.raises(NotFound, match=f"^paper {missing} not found$"):
        await workspaces.remove_paper(session, workspace.id, missing)


async def test_adding_twice_and_removing_an_absent_paper_are_no_ops(session):
    workspace = await workspaces.create(session, f"Thesis {RUN}")
    older, newer = await make_paper(session, "Older", age_days=1), await make_paper(session, "Newer")

    for paper in (older, newer, older):
        await workspaces.add_paper(session, workspace.id, paper.id)
    rows = select(func.count()).select_from(workspace_papers).where(workspace_papers.c.workspace_id == workspace.id)

    assert await session.scalar(rows) == 2
    assert [p.id for p in await workspaces.papers(session, workspace.id)] == [newer.id, older.id]
    assert older.workspace_ids == [workspace.id]

    await workspaces.remove_paper(session, workspace.id, older.id)
    await workspaces.remove_paper(session, workspace.id, older.id)

    assert [p.id for p in await workspaces.papers(session, workspace.id)] == [newer.id]
    assert older.workspace_ids == []


async def test_deleting_a_workspace_keeps_its_papers_and_notes(session):
    workspace = await workspaces.create(session, f"Thesis {RUN}")
    paper = await make_paper(session)
    await workspaces.add_paper(session, workspace.id, paper.id)
    note = await note_on(session, paper)

    await workspaces.delete(session, workspace.id)

    assert await session.get(Paper, paper.id) is not None
    assert [n.id for n in await notes.list_notes_for_paper(session, paper.id)] == [note.id]
    with pytest.raises(NotFound):
        await workspaces.get(session, workspace.id)


async def test_notes_appear_once_by_paper_title_then_reading_order(session):
    workspace = await workspaces.create(session, f"Thesis {RUN}")
    bert, attention = await make_paper(session, "BERT"), await make_paper(session, "Attention")
    outside = await make_paper(session, "Not in the workspace")
    for paper in (bert, attention):
        await workspaces.add_paper(session, workspace.id, paper.id)
    bert_p1 = await note_on(session, bert, page=1)
    attention_p2 = await note_on(session, attention, page=2)
    attention_p1_low = await note_on(session, attention, page=1, top=500)
    await note_on(session, outside)
    # A promoted note anchored on both workspace papers.
    shared = Note(body="both", provenance=Provenance.LLM)
    session.add(shared)
    await session.flush()
    await session.execute(
        insert(note_anchors),
        [
            {"note_id": shared.id, "paper_id": pid, "page": 1, "bbox": [[1, 50, 3, 60]], "quoted_text": "q"}
            for pid in (bert.id, attention.id)
        ],
    )
    await session.commit()

    listed = await workspaces.notes(session, workspace.id)

    assert [n.id for n in listed] == [shared.id, attention_p1_low.id, attention_p2.id, bert_p1.id]
    assert {a.paper_id for a in listed[0].anchors} == {bert.id, attention.id}


async def test_by_name_finds_the_workspace_with_exactly_that_name(session):
    thesis = await workspaces.create(session, f"Thesis {RUN}")
    await workspaces.create(session, f"thesis {RUN}")

    assert await workspaces.by_name(session, f"  Thesis {RUN} ") == thesis.id


async def test_by_name_for_an_unknown_name_lists_every_name(session):
    await workspaces.create(session, f"Alpha review {RUN}")

    with pytest.raises(NotFound, match="^unknown_workspace$") as unknown:
        await workspaces.by_name(session, f"No such workspace {RUN}")

    # Not compared with a later read: a workspace another run commits in between (E2E on this stack) would differ.
    available = unknown.value.details["available"]
    assert unknown.value.details == {"available": available}
    assert f"Alpha review {RUN}" in available  # the database's collation, not Python's sort, orders the names
