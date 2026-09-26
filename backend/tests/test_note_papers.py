"""A note's papers (D95): note_papers is the one list of them, and a passage can only sit on a linked paper."""

import uuid
from datetime import datetime, timedelta

import pytest
from pdf_papers import TWO_LINE_QUOTE, chunked_paper
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from test_chart_notes import bar, two_columns

from app.core import charts, datasets, notes
from app.core.errors import NotFound
from app.models import Chunk, LLMOutput, Note, Paper, Provenance, note_anchors, note_papers

pytestmark = pytest.mark.anyio

# notes.created_at is mapped without a timezone, and the test transaction freezes now(): notes that need an order get
# their own naive created_at.
NOW = datetime(2026, 9, 17, 12, 0)
RECT = [[72.0, 400.0, 290.0, 410.0]]


async def make_paper(session, title="Linked paper") -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", page_count=3)
    session.add(paper)
    await session.commit()
    return paper


async def linked(session, note_id) -> set[uuid.UUID]:
    return set(await session.scalars(select(note_papers.c.paper_id).where(note_papers.c.note_id == note_id)))


async def paper_only_note(
    session, *papers: Paper, body="On the whole paper.", provenance=Provenance.HUMAN, created=NOW
) -> Note:
    """A note linked to these papers (or none) with no passage on any: what set_papers makes."""
    note = Note(body=body, provenance=provenance, created_at=created, updated_at=created)
    session.add(note)
    await session.flush()
    if papers:
        await session.execute(insert(note_papers), [{"note_id": note.id, "paper_id": p.id} for p in papers])
    await session.commit()
    # Its dates as the database gives them back (timezone-aware), like every note a service returns: a naive and an
    # aware datetime don't compare.
    await session.refresh(note)
    return note


def anchor_row(note_id, paper_id, page=1) -> dict:
    return {"note_id": note_id, "paper_id": paper_id, "page": page, "bbox": RECT, "quoted_text": "q"}


async def test_a_human_note_links_its_paper(session):
    paper = await make_paper(session)

    note = await notes.create_human_note(session, "mine", notes.Anchor(paper.id, 1, [tuple(RECT[0])], "a quote"))

    assert await linked(session, note.id) == {paper.id}


async def test_a_promoted_note_links_the_paper_of_its_chunks(session):
    paper = await make_paper(session)
    chunks = [
        Chunk(paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100, 300, 120]], text=f"chunk {i}",
              embed_model="test", strategy_ver=1)
        for i in range(2)
    ]  # fmt: skip
    session.add_all(chunks)
    await session.flush()
    output = LLMOutput(paper_id=paper.id, kind="chat", question="q", content="It says so [C1][C2].", model="m",
                       prompt_version=2, source_chunks=[c.id for c in chunks])  # fmt: skip
    session.add(output)
    await session.commit()

    note = await notes.promote_llm_fragment(session, output.id, "It says so [C1][C2].", [c.id for c in chunks])

    assert await linked(session, note.id) == {paper.id}


async def test_a_chart_note_links_every_paper_it_is_anchored_on(session):
    bert, xlnet = await make_paper(session, "BERT"), await make_paper(session, "XLNet")
    mine = await datasets.create_dataset(session, "My runs", "user", two_columns(("mine", "92")))
    chart = await charts.create_chart(session, "F1", bar(mine))
    anchors = [notes.Anchor(p.id, 1, [tuple(RECT[0])], "Table 1") for p in (bert, xlnet)]

    note = await notes.create_chart_note(session, chart.id, anchors)

    assert await linked(session, note.id) == {bert.id, xlnet.id}


async def test_an_mcp_note_links_its_paper(session, tmp_path):
    paper, _, _ = await chunked_paper(session, tmp_path)

    note = await notes.create_llm_note(session, paper.id, "Grounding makes answers checkable.", TWO_LINE_QUOTE)

    assert await linked(session, note.id) == {paper.id}


async def test_an_anchor_on_a_paper_the_note_is_not_linked_to_is_refused(session):
    paper = await make_paper(session)
    note = await paper_only_note(session)

    with pytest.raises(IntegrityError, match="note_anchors_note_paper_fkey"):
        await session.execute(insert(note_anchors).values(anchor_row(note.id, paper.id)))


async def test_unlinking_a_paper_removes_the_notes_passages_on_it_only(session):
    kept, dropped = await make_paper(session, "Kept"), await make_paper(session, "Dropped")
    note = await paper_only_note(session, kept, dropped)
    await session.execute(insert(note_anchors), [anchor_row(note.id, kept.id), anchor_row(note.id, dropped.id, 2)])

    await session.execute(
        delete(note_papers).where(note_papers.c.note_id == note.id, note_papers.c.paper_id == dropped.id)
    )

    left = await session.scalars(select(note_anchors.c.paper_id).where(note_anchors.c.note_id == note.id))
    assert list(left) == [kept.id]


async def test_deleting_a_paper_keeps_the_note_with_no_links(session):
    paper = await make_paper(session)
    note = await paper_only_note(session, paper)
    await session.execute(insert(note_anchors).values(anchor_row(note.id, paper.id)))

    await session.execute(delete(Paper).where(Paper.id == paper.id))

    # A query, not session.get: get would answer from the identity map without asking the database.
    assert await session.scalar(select(func.count()).select_from(Note).where(Note.id == note.id)) == 1
    assert await linked(session, note.id) == set()


async def test_one_block_of_one_answer_is_saved_once_and_null_blocks_never_clash(session):
    paper = await make_paper(session)
    output = LLMOutput(paper_id=paper.id, kind="chat", content="c", model="m", prompt_version=3)
    session.add(output)
    await session.flush()
    session.add_all([
        Note(body="a", provenance="llm", source_id=output.id),
        Note(body="b", provenance="llm", source_id=output.id),  # two NULL blocks on one answer are fine
        Note(body="c", provenance="llm", source_id=output.id, source_block=0),
    ])  # fmt: skip
    await session.flush()

    session.add(Note(body="d", provenance="llm", source_id=output.id, source_block=0))
    with pytest.raises(IntegrityError, match="notes_source_block"):
        await session.flush()


async def test_a_note_lists_its_papers_by_title_then_id(session):
    zeta, alpha = await make_paper(session, "Zeta"), await make_paper(session, "Alpha")
    note = await paper_only_note(session, zeta, alpha)

    [view] = await notes.list_notes_for_paper(session, zeta.id)

    assert (view.id, view.paper_ids, view.anchors) == (note.id, [alpha.id, zeta.id], [])


async def test_a_papers_notes_on_the_whole_paper_come_first_newest_first_then_the_rest_in_reading_order(session):
    paper = await make_paper(session)
    low = await notes.create_human_note(session, "low", notes.Anchor(paper.id, 1, [(72.0, 500.0, 290.0, 510.0)], "q"))
    high = await notes.create_human_note(session, "high", notes.Anchor(paper.id, 1, [(72.0, 90.0, 290.0, 99.0)], "q"))
    older = await paper_only_note(session, paper, body="older", created=NOW - timedelta(days=2))
    newer = await paper_only_note(session, paper, body="newer", created=NOW - timedelta(days=1))

    listed = await notes.list_notes_for_paper(session, paper.id)

    assert [n.id for n in listed] == [newer.id, older.id, high.id, low.id]


async def test_set_papers_adds_and_removes_links_and_drops_the_passages_on_a_removed_paper_only(session):
    kept, dropped = await make_paper(session, "Kept"), await make_paper(session, "Dropped")
    added = await make_paper(session, "Added")
    note = await notes.create_human_note(session, "mine", notes.Anchor(kept.id, 1, [tuple(RECT[0])], "q"))
    await session.execute(insert(note_papers).values(note_id=note.id, paper_id=dropped.id))
    await session.execute(insert(note_anchors).values(anchor_row(note.id, dropped.id, page=2)))

    view = await notes.set_papers(session, note.id, [kept.id, added.id, added.id])

    assert view.paper_ids == [added.id, kept.id]  # by title; the duplicate counted once
    assert [(a.paper_id, a.page) for a in view.anchors] == [(kept.id, 1)]


async def test_set_papers_with_an_empty_list_removes_every_link_and_the_passages_they_held(session):
    paper = await make_paper(session)
    note = await notes.create_human_note(session, "mine", notes.Anchor(paper.id, 1, [tuple(RECT[0])], "q"))
    # The test transaction freezes now(): backdate so set_papers' own now() reads as later.
    old = NOW - timedelta(days=1)
    await session.execute(update(Note).where(Note.id == note.id).values(created_at=old, updated_at=old))
    [before] = await notes.list_notes_for_paper(session, paper.id)

    view = await notes.set_papers(session, note.id, [])

    assert view.paper_ids == [] and view.anchors == []
    assert await linked(session, note.id) == set()
    left = select(func.count()).select_from(note_anchors).where(note_anchors.c.note_id == note.id)
    assert await session.scalar(left) == 0
    assert view.updated_at > before.updated_at


async def test_set_papers_refuses_an_unknown_note_or_paper_and_changes_nothing(session):
    paper = await make_paper(session)
    note = await paper_only_note(session, paper)

    with pytest.raises(NotFound, match="^note .* not found$"):
        await notes.set_papers(session, uuid.uuid4(), [paper.id])
    with pytest.raises(NotFound, match="^unknown_paper$"):
        await notes.set_papers(session, note.id, [paper.id, uuid.uuid4()])

    assert await linked(session, note.id) == {paper.id}


async def test_set_papers_keeps_provenance_and_moves_updated_at_only_when_the_papers_change(session):
    paper, other = await make_paper(session, "P"), await make_paper(session, "O")
    note = await paper_only_note(session, paper, provenance=Provenance.LLM, created=NOW - timedelta(days=30))
    [before] = await notes.list_notes_for_paper(session, paper.id)

    same = await notes.set_papers(session, note.id, [paper.id])
    moved = await notes.set_papers(session, note.id, [other.id])

    assert (same.provenance, same.updated_at) == (Provenance.LLM, before.updated_at)
    assert (moved.provenance, moved.paper_ids) == (Provenance.LLM, [other.id])
    assert moved.updated_at > before.updated_at


async def test_list_notes_gives_every_note_a_papers_notes_or_the_notes_on_no_paper_newest_first(session):
    paper, other = await make_paper(session, "P"), await make_paper(session, "O")
    oldest = await paper_only_note(session, paper, created=NOW - timedelta(days=3))
    middle = await paper_only_note(session, other, created=NOW - timedelta(days=2))
    newest = await paper_only_note(session, created=NOW - timedelta(days=1))
    mine = {oldest.id, middle.id, newest.id}  # the dev database holds the owner's notes too (D15)

    every = [n.id for n in await notes.list_notes(session) if n.id in mine]
    on_paper = [n.id for n in await notes.list_notes(session, paper.id)]
    unlinked = [n.id for n in await notes.list_notes(session, unlinked=True) if n.id in mine]

    assert every == [newest.id, middle.id, oldest.id]
    assert on_paper == [oldest.id]
    assert unlinked == [newest.id]
    with pytest.raises(NotFound):
        await notes.list_notes(session, uuid.uuid4())
