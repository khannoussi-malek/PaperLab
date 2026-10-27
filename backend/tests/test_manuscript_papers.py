import asyncio
import uuid

import pytest
from conftest import TEST_DATABASE_URL, FakeEmbedder, unit_vector
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import manuscript_papers as mp
from app.core import manuscripts, workspaces
from app.core.errors import Conflict, NotFound
from app.core.manuscript_bib import build_bib
from app.models import (
    Chunk,
    Manuscript,
    ManuscriptCiteKey,
    Note,
    Paper,
    Provenance,
    Workspace,
    note_anchors,
    note_papers,
)

pytestmark = pytest.mark.anyio


async def setup(session, *titles, with_ws=True, pdf=True, name="W"):
    ws = Workspace(name=name)
    session.add(ws)
    await session.flush()
    papers = []
    for title in titles:
        p = Paper(title=title, file_path="/x.pdf" if pdf else None, authors=["Jane Smith"], year=2021)
        session.add(p)
        await session.flush()
        await workspaces.add_paper(session, ws.id, p.id)
        papers.append(p)
    m = await manuscripts.create(session, title="M", template="article", workspace_id=ws.id if with_ws else None)
    return ws, papers, m


async def note(session, provenance, paper, anchored=False):
    n = Note(body="b", provenance=provenance)
    session.add(n)
    await session.flush()
    await session.execute(insert(note_papers).values(note_id=n.id, paper_id=paper.id))
    if anchored:
        await session.execute(insert(note_anchors).values(
            note_id=n.id, paper_id=paper.id, page=1, bbox=[1, 2, 3, 4], quoted_text="q"))
    return n


async def test_keys_equal_the_bib_keys_pinned_or_not(session):
    _, papers, m = await setup(session, "Deep learning", "Deep nets")
    before = {r["paper_id"]: r["key"] for r in await mp.list_papers(session, m.id)}
    assert not any(r["pinned"] for r in await mp.list_papers(session, m.id))
    key = await mp.pin(session, m.id, papers[1].id)
    after = {r["paper_id"]: r for r in await mp.list_papers(session, m.id)}
    assert after[papers[1].id]["key"] == key == before[papers[1].id] and after[papers[1].id]["pinned"]
    assert not after[papers[0].id]["pinned"]
    bib = await build_bib(session, m, {})
    assert f"{{{key}," in bib


async def test_pin_is_idempotent_and_refuses_unknown_papers(session):
    _, papers, m = await setup(session, "A")
    assert await mp.pin(session, m.id, papers[0].id) == await mp.pin(session, m.id, papers[0].id)
    other = Paper(title="Elsewhere")
    session.add(other)
    await session.flush()
    with pytest.raises(NotFound):
        await mp.pin(session, m.id, other.id)


async def test_counts_split_highlights_notes_and_ai(session):
    _, (a, b), m = await setup(session, "A", "B", pdf=False)
    await note(session, Provenance.HUMAN, a, anchored=True)
    await note(session, Provenance.HUMAN, a)
    await note(session, Provenance.HUMAN, a)
    await note(session, Provenance.LLM, a, anchored=True)
    await note(session, Provenance.LLM_EDITED, a)
    rows = {r["paper_id"]: r for r in await mp.list_papers(session, m.id)}
    assert (rows[a.id]["highlights"], rows[a.id]["notes"], rows[a.id]["ai_notes"]) == (1, 2, 2)
    assert (rows[b.id]["highlights"], rows[b.id]["notes"], rows[b.id]["ai_notes"]) == (0, 0, 0)
    assert rows[b.id]["has_pdf"] is False and rows[b.id]["first_author"] == "Jane Smith" and rows[b.id]["year"] == 2021


async def test_a_workspaceless_manuscript_lists_only_pinned_papers(session):
    _, (a, _), m = await setup(session, "A", "B")
    loose = await manuscripts.create(session, title="L", template="article", workspace_id=None)
    assert await mp.list_papers(session, loose.id) == []
    assert await mp.rank(session, loose.id, "anything") == []
    await mp.pin(session, m.id, a.id)
    await manuscripts.update(session, m.id, workspace_id=None)
    rows = await mp.list_papers(session, m.id)
    assert [(r["paper_id"], r["pinned"]) for r in rows] == [(a.id, True)]


async def test_rank_orders_by_relevance_and_dedupes(session, embedder):
    _, (a, b, c), m = await setup(session, "A", "B", "C")
    embedder.vectors["search_query: intro"] = unit_vector("intro")
    for paper, vec in ((b, unit_vector("intro")), (a, unit_vector("far"))):
        for i in range(2):
            session.add(Chunk(paper_id=paper.id, ordinal=i, page=1, bbox=[[1, 2, 3, 4]], text="t", embedding=vec,
                              embed_model="test", strategy_ver=1))
    await session.flush()
    ids = await mp.rank(session, m.id, "intro", embedder=embedder)
    assert ids[:2] == [str(b.id), str(a.id)] and len(ids) == len(set(ids)) and str(c.id) not in ids
    assert await mp.rank(session, m.id, "  ", embedder=embedder) == []


async def test_rank_propagates_a_failing_search_source(session):
    _, _, m = await setup(session, "A")
    with pytest.raises(Conflict):
        await mp.rank(session, m.id, "x", embedder=FakeEmbedder(refuse="down"))


async def test_pinning_twice_leaves_one_row_and_one_key(session):
    _, (a, _), m = await setup(session, "A", "B")
    keys = [await mp.pin(session, m.id, a.id) for _ in range(2)]
    rows = await session.scalar(select(func.count()).select_from(ManuscriptCiteKey).where(
        ManuscriptCiteKey.manuscript_id == m.id))
    assert keys[0] == keys[1] and rows == 1


async def test_papers_with_the_same_base_key_get_distinct_pinned_keys(session):
    _, (a, b), m = await setup(session, "Deep learning", "Deep learning too")
    keys = {await mp.pin(session, m.id, a.id), await mp.pin(session, m.id, b.id)}
    assert len(keys) == 2
    assert {r["key"] for r in await mp.list_papers(session, m.id)} == keys


async def test_a_note_anchored_on_one_of_its_papers_is_a_note_on_the_other(session):
    _, (a, b), m = await setup(session, "A", "B")
    n = await note(session, Provenance.HUMAN, a, anchored=True)
    await session.execute(insert(note_papers).values(note_id=n.id, paper_id=b.id))
    rows = {r["paper_id"]: r for r in await mp.list_papers(session, m.id)}
    assert (rows[a.id]["highlights"], rows[a.id]["notes"]) == (1, 0)
    assert (rows[b.id]["highlights"], rows[b.id]["notes"]) == (0, 1)


@pytest.mark.xdist_group("manuscript_rows")  # commits real rows on separate connections
async def test_a_bib_built_while_a_pin_is_open_waits_for_it_and_leaves_one_row():
    """Export's build_bib racing a pin: the rolled-back shared session can't show locking, so two real ones."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        ws, (paper,), m = await setup(s, "Racing pins", name=f"race {uuid.uuid4()}")  # committed: a name of its own
        await s.commit()
    try:
        async with maker() as pinning, maker() as exporting:
            key = await mp.pin(pinning, m.id, paper.id)  # its transaction holds the manuscript row
            manuscript = await exporting.get(Manuscript, m.id)
            racing = asyncio.create_task(build_bib(exporting, manuscript, {"main.tex": f"\\cite{{{key}}}"}))
            await asyncio.sleep(0.3)
            assert not racing.done()  # waits for the pin
            await pinning.commit()
            assert f"{{{key}," in await racing
            await exporting.commit()
        async with maker() as s:
            rows = await s.scalar(select(func.count()).select_from(ManuscriptCiteKey).where(
                ManuscriptCiteKey.manuscript_id == m.id))
        assert rows == 1
    finally:
        async with maker() as s:
            await s.execute(delete(Manuscript).where(Manuscript.id == m.id))
            await s.execute(delete(Workspace).where(Workspace.id == ws.id))
            await s.execute(delete(Paper).where(Paper.id == paper.id))
            await s.commit()
        await engine.dispose()


@pytest.mark.xdist_group("manuscript_rows")  # commits real rows on separate connections
async def test_a_compile_building_the_bib_and_a_new_file_saved_meanwhile_both_finish():
    """The worker's pass has UPDATEd the manuscript (FOR NO KEY UPDATE) when build_bib runs; a file insert meanwhile
    holds FOR KEY SHARE (its foreign key) and waits to bump the manuscript. A plain FOR UPDATE here deadlocked."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        ws, papers, m = await setup(s, "Locks", name=f"locks {uuid.uuid4()}")
        await s.commit()
    try:
        async with maker() as compiling, maker() as saving:
            manuscript = await compiling.get(Manuscript, m.id)
            manuscript.compile_status = "running"
            await compiling.flush()  # as _prepare: the row is held FOR NO KEY UPDATE
            insert_file = asyncio.create_task(
                manuscripts._store(saving, m.id, "new.tex", None, text="x", data=None))
            await asyncio.sleep(0.3)
            assert not insert_file.done()  # inserted, now waiting to bump the manuscript
            await asyncio.wait_for(build_bib(compiling, manuscript, {}), 5)
            await compiling.commit()
            await asyncio.wait_for(insert_file, 5)
            await saving.commit()
    finally:
        async with maker() as s:
            await s.execute(delete(Manuscript).where(Manuscript.id == m.id))
            await s.execute(delete(Workspace).where(Workspace.id == ws.id))
            await s.execute(delete(Paper).where(Paper.id.in_([p.id for p in papers])))
            await s.commit()
        await engine.dispose()
