import numpy as np
import pytest
from conftest import unit_vector

from app.core.retrieval import retrieve
from app.models import Chunk, Paper
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
