import uuid
from collections import Counter

import numpy as np
import pytest
from conftest import unit_vector
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, insert, text

from app.core import retrieval
from app.core.retrieval import retrieve
from app.models import Chunk, Paper, Workspace, workspace_papers
from app.providers import embedding

pytestmark = pytest.mark.anyio

QUERY = "how does attention work?"


def near(query: list[float], spread: float, seed: str) -> list[float]:
    """A unit vector at a small, spread-dependent distance from the query.

    Real chunks already in the dev database sit at distance ~1 from a random query, so they never
    reach the top k of these.
    """
    vector = np.array(query) + spread * np.array(unit_vector(seed))
    return (vector / np.linalg.norm(vector)).tolist()


async def seed_papers(session, embedder):
    """Papers A and B, six embedded chunks each at interleaved distances, plus one unembedded chunk in A."""
    query = unit_vector("query")
    embedder.vectors[f"search_query: {QUERY}"] = query
    papers = [Paper(title=name, file_path=f"/{name}.pdf", status="ready") for name in ("A", "B")]
    session.add_all(papers)
    await session.flush()
    chunks = [
        Chunk(
            paper_id=paper.id,
            ordinal=i,
            page=i + 1,
            bbox=[[10, 20, 30, 40]],
            section_title="Method" if i % 2 else None,
            text=f"{paper.title} chunk {i}",
            embedding=near(query, 0.1 * (2 * i + offset + 1), f"{paper.title}{i}"),
            embed_model="test",
            strategy_ver=1,
        )
        for offset, paper in enumerate(papers)
        for i in range(6)
    ]
    unembedded = Chunk(
        paper_id=papers[0].id, ordinal=6, page=7, bbox=[[1, 2, 3, 4]], text="no vector yet", embed_model="test",
        strategy_ver=1,
    )
    session.add_all([*chunks, unembedded])
    await session.commit()
    distance = {c.id: 1 - float(np.dot(query, c.embedding)) for c in chunks}
    return papers, chunks, unembedded, distance


async def test_returns_the_true_nearest_k_in_order(session, embedder):
    _, chunks, _, distance = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, k=5, embedder=embedder)

    expected = sorted(chunks, key=lambda c: distance[c.id])[:5]
    assert [r.id for r in found] == [c.id for c in expected]
    assert [r.distance for r in found] == pytest.approx([distance[c.id] for c in expected], abs=1e-5)
    assert embedder.calls[0][0] == [f"search_query: {QUERY}"]
    first = found[0]
    assert (first.page, first.bbox, first.text) == (expected[0].page, [(10.0, 20.0, 30.0, 40.0)], expected[0].text)


async def test_paper_scope_is_respected(session, embedder):
    (paper_a, _), chunks, _, distance = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id], k=4, embedder=embedder)

    in_a = sorted((c for c in chunks if c.paper_id == paper_a.id), key=lambda c: distance[c.id])
    assert [r.id for r in found] == [c.id for c in in_a[:4]]
    assert {r.paper_id for r in found} == {paper_a.id}


async def test_chunks_without_an_embedding_are_skipped(session, embedder):
    (paper_a, _), _, unembedded, _ = await seed_papers(session, embedder)

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id], k=100, embedder=embedder)

    assert len(found) == 6
    assert unembedded.id not in {r.id for r in found}


async def test_uses_the_process_model_when_no_embedder_is_given(session, embedder, monkeypatch):
    (paper_a, _), _, _, _ = await seed_papers(session, embedder)
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)

    found = await retrieve(session, QUERY, paper_ids=[paper_a.id], k=1)
    assert len(found) == 1 and embedder.calls


def fresh_query(embedder) -> list[float]:
    """A query vector no earlier test run used.

    Rolled-back inserts leave dead HNSW entries until autovacuum. Seeded from a fixed string, thousands of
    identical dead vectors pile up around the query, and an HNSW scan gives up before reaching live rows.
    """
    query = unit_vector(uuid.uuid4().hex)
    embedder.vectors[f"search_query: {QUERY}"] = query
    return query


def at_spread(query: list[float], spread: float) -> list[float]:
    """A unit vector whose cosine distance from the query is exactly 1 - 1/sqrt(1 + spread²).

    near() adds random noise that isn't orthogonal to the query, which moves distances by ~0.007 per sigma: enough
    to swap two papers whose spreads differ by 0.05.
    """
    q = np.array(query)
    noise = np.array(unit_vector(uuid.uuid4().hex))
    noise -= noise.dot(q) * q
    vector = q + spread * noise / np.linalg.norm(noise)
    return (vector / np.linalg.norm(vector)).tolist()


async def add_paper(session, query: list[float], title: str, spreads: list[float]) -> Paper:
    """A ready paper whose chunk i sits at spreads[i] from the query, in that order of distance."""
    paper = Paper(title=title, file_path=f"/{title}.pdf", status="ready")
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(
            paper_id=paper.id, ordinal=i, page=1, bbox=[[1, 2, 3, 4]], text=f"{title} chunk {i}",
            embedding=at_spread(query, spread), embed_model="test", strategy_ver=1,
        )
        for i, spread in enumerate(spreads)
    )
    await session.commit()
    return paper


async def make_workspace(session, papers: list[Paper]) -> Workspace:
    workspace = Workspace(name=f"Retrieval {uuid.uuid4()}")  # unique: the owner's workspaces share the database
    session.add(workspace)
    await session.flush()
    if papers:  # an executemany with an empty list of rows is invalid
        rows = [{"workspace_id": workspace.id, "paper_id": p.id} for p in papers]
        await session.execute(insert(workspace_papers), rows)
    await session.commit()
    return workspace


async def test_workspace_and_multi_paper_scopes_return_only_in_scope_chunks(session, embedder):
    query = fresh_query(embedder)
    paper_a = await add_paper(session, query, "A", [0.1, 0.3, 0.5, 0.7])
    paper_b = await add_paper(session, query, "B", [0.2, 0.4, 0.6, 0.8])
    outside = await add_paper(session, query, "Outside", [0.05, 0.06])  # nearer than anything in scope
    workspace = await make_workspace(session, [paper_a, paper_b])
    await make_workspace(session, [outside])

    by_workspace = await retrieve(session, QUERY, workspace_id=workspace.id, k=6, embedder=embedder)
    by_ids = await retrieve(session, QUERY, paper_ids=[paper_a.id, paper_b.id], k=6, embedder=embedder)

    expected = ["A chunk 0", "B chunk 0", "A chunk 1", "B chunk 1", "A chunk 2", "B chunk 2"]  # 3 per paper
    assert [r.text for r in by_workspace] == expected
    assert [r.text for r in by_ids] == expected


async def test_both_scopes_at_once_is_a_value_error(session, embedder):
    with pytest.raises(ValueError, match="paper_ids or workspace_id, not both"):
        await retrieve(session, QUERY, paper_ids=[], workspace_id=uuid.uuid4(), embedder=embedder)


async def test_an_empty_paper_list_returns_nothing_without_embedding_the_query(session, embedder):
    assert await retrieve(session, QUERY, paper_ids=[], embedder=embedder) == []
    assert embedder.calls == []


async def test_k_defaults_to_8(session, embedder):
    paper = await add_paper(session, fresh_query(embedder), "Ten chunks", [0.1 * (i + 1) for i in range(10)])

    assert len(await retrieve(session, QUERY, paper_ids=[paper.id], embedder=embedder)) == 8


async def test_a_dominant_paper_gets_at_most_3_of_k(session, embedder):
    query = fresh_query(embedder)
    dominant = await add_paper(session, query, "Dominant", [0.05 + 0.01 * i for i in range(10)])
    second = await add_paper(session, query, "Second", [0.5, 0.6, 0.7, 0.8])
    third = await add_paper(session, query, "Third", [0.55, 0.65, 0.75, 0.85])
    workspace = await make_workspace(session, [dominant, second, third])
    ids = [dominant.id, second.id, third.id]

    capped = Counter(r.paper_id for r in await retrieve(session, QUERY, workspace_id=workspace.id, embedder=embedder))
    by_ids = Counter(r.paper_id for r in await retrieve(session, QUERY, paper_ids=ids, embedder=embedder))
    single = await retrieve(session, QUERY, paper_ids=[dominant.id], embedder=embedder)
    uncapped = await retrieve(session, QUERY, workspace_id=workspace.id, per_paper=8, embedder=embedder)

    assert retrieval.MAX_PER_PAPER == 3
    assert capped == by_ids == {dominant.id: 3, second.id: 3, third.id: 2}
    assert len(single) == 8  # one paper: no cap
    assert {r.paper_id for r in uncapped} == {dominant.id}


async def test_a_forced_hnsw_plan_still_returns_k_rows(session, embedder):
    """A filtered HNSW scan post-filters inside ef_search (40) candidates: 60 nearer chunks outside the scope used to
    leave 0 rows."""
    query = fresh_query(embedder)
    await add_paper(session, query, "Crowd", [0.1] * 60)
    paper_a = await add_paper(session, query, "A", [1.0] * 4)
    paper_b = await add_paper(session, query, "B", [1.0] * 4)
    workspace = await make_workspace(session, [paper_a, paper_b])
    # enable_seqscan alone still picks the (paper_id, page) btree and a sort; without sorts, HNSW is the only way.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL enable_sort = off"))
    plan = await session.execute(
        text("EXPLAIN SELECT id FROM chunks WHERE paper_id = ANY(:ids) ORDER BY embedding <=> :q LIMIT 6").bindparams(
            bindparam("q", type_=Vector(768))
        ),
        {"ids": [paper_a.id, paper_b.id], "q": query},
    )
    assert "chunks_embedding_idx" in "\n".join(row[0] for row in plan)

    by_ids = await retrieve(session, QUERY, paper_ids=[paper_a.id, paper_b.id], k=6, embedder=embedder)
    assert len(by_ids) == 6
    assert [r.distance for r in by_ids] == sorted(r.distance for r in by_ids)
    assert len(await retrieve(session, QUERY, workspace_id=workspace.id, k=6, embedder=embedder)) == 6


async def test_a_single_paper_workspace_is_not_capped(session, embedder):
    paper = await add_paper(session, fresh_query(embedder), "Solo", [0.1 * (i + 1) for i in range(10)])
    workspace = await make_workspace(session, [paper])

    found = await retrieve(session, QUERY, workspace_id=workspace.id, embedder=embedder)

    assert len(found) == 8  # k defaults to 8; a lone paper is uncapped, same as passing its id directly
    assert {r.paper_id for r in found} == {paper.id}


async def test_an_empty_workspace_returns_nothing_without_embedding_the_query(session, embedder):
    workspace = await make_workspace(session, [])

    assert await retrieve(session, QUERY, workspace_id=workspace.id, embedder=embedder) == []
    assert embedder.calls == []
