from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.models import Chunk, Paper
from app.workers import ingest

pytestmark = pytest.mark.anyio


@pytest.fixture
def worker_session(session, monkeypatch):
    """Point the worker at the rolled-back test session instead of its own SessionLocal."""

    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(ingest, "SessionLocal", shared_session)
    return session


async def add_paper(session, path, **fields) -> Paper:
    paper = Paper(file_path=str(path), **{"title": "placeholder", **fields})
    session.add(paper)
    await session.commit()
    return paper


async def chunks_of(session, paper_id):
    return list(await session.scalars(select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)))


async def test_ingest_reaches_ready_with_chunks(worker_session, sample_pdf):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper({}, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error, paper.page_count) == ("ready", None, 2)
    assert paper.title == "Deep Paper Title"
    chunks = await chunks_of(worker_session, paper.id)
    assert {c.page for c in chunks} == {1, 2}
    assert chunks[-1].section_title == "2 Method"
    assert all(c.bbox and c.embedding is None for c in chunks)


async def test_reingest_is_idempotent(worker_session, sample_pdf):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper({}, str(paper.id))
    first = [(c.ordinal, c.page, c.text) for c in await chunks_of(worker_session, paper.id)]
    await ingest.ingest_paper({}, str(paper.id))
    second = [(c.ordinal, c.page, c.text) for c in await chunks_of(worker_session, paper.id)]

    assert first == second and first


async def test_pdf_without_text_ends_failed_with_error(worker_session, blank_pdf):
    paper = await add_paper(worker_session, blank_pdf)

    await ingest.ingest_paper({}, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "failed"
    assert paper.status_error.startswith("InvalidInput: PDF has no usable text layer")
    assert await chunks_of(worker_session, paper.id) == []


async def test_missing_file_ends_failed(worker_session, tmp_path):
    paper = await add_paper(worker_session, tmp_path / "gone.pdf")

    await ingest.ingest_paper({}, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "failed" and paper.status_error


async def test_enriched_title_is_not_overwritten(worker_session, sample_pdf):
    paper = await add_paper(worker_session, sample_pdf, openalex_id="W123", title="Title From OpenAlex")

    await ingest.ingest_paper({}, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "ready" and paper.title == "Title From OpenAlex"
