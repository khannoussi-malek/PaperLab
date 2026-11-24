"""Document-aware chunk headers (M8, migration 0082): each chunk is embedded and keyword-indexed with "<title> ·
<section>" before its text, while its text stays the PDF's own. Measured 2026-11-23: chat's path found apixaban q06
and semaglutide q09 (RAG report §4)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from conftest import FakeEmbedder
from sqlalchemy import select, text

from app.core import chunk_headers, papers, queue
from app.domain.chunking import ChunkDraft
from app.models import Chunk, Paper
from app.workers import ingest
from app.workers.settings import IngestWorkerSettings

pytestmark = pytest.mark.anyio


def test_the_header_joins_title_and_section_and_skips_what_is_missing():
    assert chunk_headers.header("ELIQUIS", "7 DRUG INTERACTIONS") == "ELIQUIS · 7 DRUG INTERACTIONS"
    assert chunk_headers.header("  ELIQUIS ", None) == "ELIQUIS"
    assert chunk_headers.header(None, "Methods") == "Methods"
    assert chunk_headers.header(None, "  ") == ""


def test_the_embedded_text_puts_the_header_on_its_own_line():
    assert chunk_headers.embed_text("ELIQUIS · Dosing", "Take 5 mg.") == "ELIQUIS · Dosing\nTake 5 mg."
    assert chunk_headers.embed_text("", "Take 5 mg.") == "Take 5 mg."


async def labelled_paper(session, title: str) -> Paper:
    paper = Paper(file_path="x.pdf", title=title)
    session.add(paper)
    await session.commit()
    drafts = [
        ChunkDraft(0, 1, [[0, 0, 1, 1]], "Interactions", "Strong CYP3A4 inhibitors raise exposure."),
        ChunkDraft(1, 2, [[0, 0, 1, 1]], None, "Store below 30 °C."),
    ]
    await papers.replace_chunks(session, paper.id, drafts)
    return paper


async def chunks_of(session, paper_id) -> list[Chunk]:
    query = select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    return list(await session.scalars(query.execution_options(populate_existing=True)))


async def test_embedding_sends_header_and_text_and_keeps_the_text(worker_session, embedder):
    paper = await labelled_paper(worker_session, "Eliquis label")

    assert await ingest._embed(worker_session, paper.id, embedder)

    assert embedder.calls[0][0] == [
        "search_document: Eliquis label · Interactions\nStrong CYP3A4 inhibitors raise exposure.",
        "search_document: Eliquis label\nStore below 30 °C.",
    ]
    stored = await chunks_of(worker_session, paper.id)
    assert [c.header for c in stored] == ["Eliquis label · Interactions", "Eliquis label"]
    assert [c.text for c in stored] == ["Strong CYP3A4 inhibitors raise exposure.", "Store below 30 °C."]


async def test_a_paper_with_no_title_or_section_stores_an_empty_header(worker_session, embedder):
    paper = await labelled_paper(worker_session, "")

    await ingest._embed(worker_session, paper.id, embedder, missing_only=True)

    assert embedder.calls[0][0][1] == "search_document: Store below 30 °C."
    assert [c.header for c in await chunks_of(worker_session, paper.id)] == ["Interactions", ""]


async def test_the_keyword_index_reads_the_header(worker_session, embedder):
    paper = await labelled_paper(worker_session, "Eliquis label")
    await ingest._embed(worker_session, paper.id, embedder)

    tsv = await worker_session.scalar(
        text("SELECT tsv::text FROM chunks WHERE paper_id = :id AND ordinal = 1"), {"id": paper.id}
    )

    assert "'eliqui'" in tsv and "'store'" in tsv  # the english stemmer's eliquis


async def headed_and_old(session, embedder) -> tuple[Paper, Paper]:
    """One paper embedded with headers, one with vectors from before them (header NULL)."""
    headed = await labelled_paper(session, "Headed")
    await ingest._embed(session, headed.id, embedder)
    old = await labelled_paper(session, "Old")
    ids = [c.id for c in await chunks_of(session, old.id)]
    await papers.set_embeddings(session, ids, [[0.1] * 768] * 2, "test", None)
    await session.execute(text("UPDATE chunks SET header = NULL WHERE paper_id = :id"), {"id": old.id})
    await session.commit()
    return headed, old


async def test_a_starting_ingest_worker_queues_papers_embedded_before_headers(worker_session, embedder):
    _, old = await headed_and_old(worker_session, embedder)

    await ingest.queue_chunk_headers({})
    await ingest.queue_chunk_headers({})  # a restart: the job id keeps it to one

    assert queue._pool.jobs == [("add_chunk_headers", str(old.id))]
    assert f"chunk-headers:{old.id}" in queue._pool.job_ids


async def test_header_reembeds_are_spread_out_so_a_new_upload_never_waits_behind_them(worker_session, embedder):
    """One ingest worker runs jobs in order: each paper starts once the ones before it have had time at HEADER_PACE,
    so an upload queued now comes before every re-embed not yet due."""
    first = await labelled_paper(worker_session, "First")
    second = await labelled_paper(worker_session, "Second")
    for paper in (first, second):
        ids = [c.id for c in await chunks_of(worker_session, paper.id)]
        await papers.set_embeddings(worker_session, ids, [[0.1] * 768] * 2, "test", None)
    await worker_session.execute(text("UPDATE chunks SET header = NULL"))
    await worker_session.commit()

    await ingest.queue_chunk_headers({})

    assert len(queue._pool.jobs) == 2
    assert queue._pool.deferred == [None, 2 / ingest.HEADER_PACE]  # the first now, the next after its 2 chunks


async def test_a_cloud_search_source_is_never_billed_for_headers(worker_session, embedder, monkeypatch):
    await headed_and_old(worker_session, embedder)

    async def cloud(session):
        return type("Source", (), {"is_local": False})()

    monkeypatch.setattr(ingest.embedding_sources, "active", cloud)

    await ingest.queue_chunk_headers({})

    assert queue._pool.jobs == []


async def test_the_header_job_embeds_only_the_chunks_still_without_one(worker_session, embedder):
    """So a big paper cut short by the job's deadline resumes where it stopped."""
    _, old = await headed_and_old(worker_session, embedder)
    first = (await chunks_of(worker_session, old.id))[0]
    await worker_session.execute(text("UPDATE chunks SET header = 'done' WHERE id = :id"), {"id": first.id})
    await worker_session.commit()
    fresh = FakeEmbedder()

    await ingest.add_chunk_headers({"embedder": fresh}, str(old.id))

    assert fresh.calls == [(["search_document: Old\nStore below 30 °C."], {})]
    assert [c.header for c in await chunks_of(worker_session, old.id)] == ["done", "Old"]


async def test_the_header_job_does_nothing_for_a_paper_gone_since_or_a_cloud_source(worker_session, embedder):
    _, old = await headed_and_old(worker_session, embedder)
    cloud = FakeEmbedder(is_local=False)

    await ingest.add_chunk_headers({"embedder": embedder}, str(uuid.uuid4()))  # deleted after it was queued
    await ingest.add_chunk_headers({"embedder": cloud}, str(old.id))  # switched to a cloud source meanwhile

    assert cloud.calls == []
    assert [c.header for c in await chunks_of(worker_session, old.id)] == [None, None]


async def test_a_database_error_at_startup_still_starts_the_ingest_worker(worker_session, monkeypatch, caplog):
    async def down(session):
        raise ConnectionRefusedError("database down")

    monkeypatch.setattr(ingest.embedding_sources, "active", down)
    redis = AsyncMock(zrange=AsyncMock(return_value=[b"abc"]))

    await IngestWorkerSettings.on_startup({"redis": redis})  # no exception: the worker starts

    redis.delete.assert_awaited_once_with("arq:in-progress:abc")
    assert "queueing chunk-header re-embeds failed" in caplog.text
