from contextlib import asynccontextmanager

import numpy as np
import pytest
from conftest import unit_vector
from sqlalchemy import select

from app.models import Chunk, Paper
from app.providers import embedding
from app.workers import ingest
from app.workers.settings import WorkerSettings

pytestmark = pytest.mark.anyio


@pytest.fixture
def worker_session(session, monkeypatch):
    """Point the worker at the rolled-back test session instead of its own SessionLocal."""

    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(ingest, "SessionLocal", shared_session)
    return session


@pytest.fixture
def ctx(embedder):
    """What WorkerSettings.on_startup leaves in the ARQ context, with the fake model."""
    return {"embedder": embedder}


async def add_paper(session, path, **fields) -> Paper:
    paper = Paper(file_path=str(path), **{"title": "placeholder", **fields})
    session.add(paper)
    await session.commit()
    return paper


async def chunks_of(session, paper_id):
    # populate_existing: embeddings are written by a bulk UPDATE, which leaves loaded objects stale.
    query = select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    return list(await session.scalars(query.execution_options(populate_existing=True)))


async def test_ingest_reaches_ready_with_embedded_chunks(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error, paper.page_count) == ("ready", None, 2)
    assert paper.title == "Deep Paper Title"
    chunks = await chunks_of(worker_session, paper.id)
    assert {c.page for c in chunks} == {1, 2}
    assert chunks[-1].section_title == "2 Method"
    assert all(c.bbox and c.embedding is not None for c in chunks)


async def test_chunks_are_embedded_with_the_document_prefix(worker_session, sample_pdf, ctx, embedder):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))

    chunks = await chunks_of(worker_session, paper.id)
    prefixed = [f"search_document: {c.text}" for c in chunks]
    assert embedder.calls == [(prefixed, {"batch_size": 16, "normalize_embeddings": True})]
    for chunk, text in zip(chunks, prefixed):
        assert np.allclose(chunk.embedding, unit_vector(text), atol=1e-6)


async def test_model_loads_once_per_worker_not_per_job(worker_session, sample_pdf, embedder, monkeypatch):
    loads = []
    monkeypatch.setattr(embedding, "load", lambda: loads.append("load") or embedder)
    paper = await add_paper(worker_session, sample_pdf)
    worker_ctx = {}

    await WorkerSettings.on_startup(worker_ctx)
    await ingest.ingest_paper(worker_ctx, str(paper.id))
    await ingest.ingest_paper(worker_ctx, str(paper.id))

    assert loads == ["load"]
    assert len(embedder.calls) == 2


async def test_reingest_is_idempotent(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))
    first = [(c.ordinal, c.page, c.text) for c in await chunks_of(worker_session, paper.id)]
    await ingest.ingest_paper(ctx, str(paper.id))
    second = [(c.ordinal, c.page, c.text) for c in await chunks_of(worker_session, paper.id)]

    assert first == second and first


async def test_reingest_replaces_the_vectors(worker_session, sample_pdf, ctx, embedder):
    paper = await add_paper(worker_session, sample_pdf)
    await ingest.ingest_paper(ctx, str(paper.id))
    first = await chunks_of(worker_session, paper.id)

    # A different model version: every text now embeds to another vector.
    embedder.vectors = {f"search_document: {c.text}": unit_vector(f"v2 {c.text}") for c in first}
    await ingest.ingest_paper(ctx, str(paper.id))
    second = await chunks_of(worker_session, paper.id)

    assert {c.id for c in first}.isdisjoint(c.id for c in second)
    for chunk in second:
        assert np.allclose(chunk.embedding, unit_vector(f"v2 {chunk.text}"), atol=1e-6)


async def test_embedder_failure_ends_failed_with_error(worker_session, sample_pdf):
    class ExplodingEmbedder:
        def encode(self, texts, **kwargs):
            raise RuntimeError("model ran out of memory")

    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper({"embedder": ExplodingEmbedder()}, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error) == ("failed", "RuntimeError: model ran out of memory")


async def test_pdf_without_text_ends_failed_with_error(worker_session, blank_pdf, ctx):
    paper = await add_paper(worker_session, blank_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "failed"
    assert paper.status_error.startswith("InvalidInput: PDF has no usable text layer")
    assert await chunks_of(worker_session, paper.id) == []


async def test_missing_file_ends_failed(worker_session, tmp_path, ctx):
    paper = await add_paper(worker_session, tmp_path / "gone.pdf")

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "failed" and paper.status_error


async def test_enriched_title_is_not_overwritten(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf, openalex_id="W123", title="Title From OpenAlex")

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "ready" and paper.title == "Title From OpenAlex"
