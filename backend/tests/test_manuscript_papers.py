import pytest
from conftest import FakeEmbedder, unit_vector
from sqlalchemy import func, insert, select

from app.core import manuscript_papers as mp
from app.core import manuscripts, workspaces
from app.core.errors import Conflict, NotFound
from app.core.manuscript_bib import build_bib
from app.models import Chunk, ManuscriptCiteKey, Note, Paper, Provenance, Workspace, note_anchors, note_papers

pytestmark = pytest.mark.anyio


async def setup(session, *titles, with_ws=True, pdf=True):
    ws = Workspace(name="W")
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
