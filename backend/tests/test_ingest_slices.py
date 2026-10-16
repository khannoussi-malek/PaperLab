import asyncio

import numpy as np
import pytest
from conftest import FakeEmbedder, unit_vector
from sqlalchemy import select

from app.core import embedding_sources, papers
from app.core.chunking import ChunkDraft
from app.models import Chunk, Paper
from app.workers import ingest

pytestmark = pytest.mark.anyio


async def paper_with_chunks(session, count: int) -> Paper:
    paper = Paper(file_path="x.pdf", title="slices")
    session.add(paper)
    await session.commit()
    drafts = [ChunkDraft(i, 1, [[0, 0, 1, 1]], None, f"text {i}") for i in range(count)]
    await papers.replace_chunks(session, paper.id, drafts)
    return paper


async def vectors_of(session, paper_id):
    query = select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    return list(await session.scalars(query.execution_options(populate_existing=True)))


class SleepingEmbedder(FakeEmbedder):
    def __init__(self, delay: float):
        super().__init__()
        self.delay = delay

    async def encode(self, texts):
        await asyncio.sleep(self.delay)
        return await super().encode(texts)


async def test_embedding_writes_in_slices_of_64(worker_session, embedder, monkeypatch):
    paper = await paper_with_chunks(worker_session, 150)
    writes = []
    real = papers.set_embeddings

    async def record(session, ids, vectors, name):
        writes.append(len(ids))
        await real(session, ids, vectors, name)

    monkeypatch.setattr(papers, "set_embeddings", record)

    assert await ingest._embed(worker_session, paper.id, embedder) is True

    assert [len(texts) for texts, _ in embedder.calls] == [64, 64, 22]
    assert writes == [64, 64, 22]


async def test_sliced_vectors_equal_unsliced(worker_session, embedder):
    paper = await paper_with_chunks(worker_session, 150)

    await ingest._embed(worker_session, paper.id, embedder)

    for chunk in await vectors_of(worker_session, paper.id):
        assert np.allclose(chunk.embedding, unit_vector(f"search_document: {chunk.text}"), atol=1e-6)


async def test_a_source_switch_mid_embed_stops_further_writes(worker_session, embedder, monkeypatch):
    paper = await paper_with_chunks(worker_session, 150)
    seen = 0

    async def active_name(session):
        nonlocal seen
        seen += 1
        return embedder.name if seen == 1 else "switched"

    monkeypatch.setattr(embedding_sources, "active_name", active_name)

    assert await ingest._embed(worker_session, paper.id, embedder) is False

    written = [c for c in await vectors_of(worker_session, paper.id) if c.embedding is not None]
    assert len(written) == 64


async def test_each_slice_is_a_cancellation_point(worker_session):
    paper = await paper_with_chunks(worker_session, 150)
    slow = SleepingEmbedder(0.3)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.45):
            await ingest._embed(worker_session, paper.id, slow)

    written = [c for c in await vectors_of(worker_session, paper.id) if c.embedding is not None]
    assert len(written) == 64
