import asyncio
import uuid

import numpy as np
import pytest
from arq.worker import Retry
from conftest import FakeArq, FakeEmbedder, unit_vector
from sqlalchemy import select

from app.core import embedding_sources, papers, queue
from app.core.chunking import ChunkDraft
from app.models import Chunk, Paper, PaperStatus
from app.workers import ingest
from app.workers.settings import IngestWorkerSettings

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


class HangingEmbedder(FakeEmbedder):
    """Answers its first slice, then never the second: the deadline, not a race against a sleep, ends the job."""

    def __init__(self):
        super().__init__()
        self.slices = 0

    async def encode(self, texts):
        self.slices += 1
        if self.slices > 1:
            await asyncio.Event().wait()
        return await super().encode(texts)


DEADLINE = 2.0  # seconds: room for an extract, a chunking and a slice's write on a loaded machine


def short_deadline(monkeypatch) -> None:
    monkeypatch.setattr(ingest, "INGEST_JOB_TIMEOUT", DEADLINE)


def record_writes(monkeypatch) -> list[int]:
    writes = []
    real = papers.set_embeddings

    async def record(session, ids, vectors, name):
        writes.append(len(ids))
        await real(session, ids, vectors, name)

    monkeypatch.setattr(papers, "set_embeddings", record)
    return writes


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


async def test_a_deadline_between_slices_keeps_earlier_slices(worker_session):
    paper = await paper_with_chunks(worker_session, 150)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(DEADLINE):
            await ingest._embed(worker_session, paper.id, HangingEmbedder())

    written = [c for c in await vectors_of(worker_session, paper.id) if c.embedding is not None]
    assert len(written) == 64


async def slow_ingest(worker_session, sample_pdf, monkeypatch):
    """A paper and an embedder that hangs after its first of two one-chunk slices. The caller sets the short deadline
    (`short_deadline`) when the hang should end the job, after any setup ingest that must not run under it."""
    monkeypatch.setattr(ingest, "EMBED_WRITE_BATCH", 1)
    paper = Paper(file_path=str(sample_pdf), title="placeholder")
    worker_session.add(paper)
    await worker_session.commit()
    return paper, HangingEmbedder()


async def test_an_ingest_past_its_deadline_is_marked_failed(worker_session, sample_pdf, monkeypatch):
    paper, slow = await slow_ingest(worker_session, sample_pdf, monkeypatch)
    short_deadline(monkeypatch)
    writes = record_writes(monkeypatch)

    assert await ingest.ingest_paper({"embedder": slow}, str(paper.id)) is None  # arq finishes the job
    await worker_session.refresh(paper)

    assert writes == [1]  # a slice was written before the deadline, so the clearing below is real
    assert (paper.status, paper.status_error) == ("failed", ingest.timed_out(DEADLINE))
    chunks = await vectors_of(worker_session, paper.id)
    assert len(chunks) > 1 and all(c.embedding is None for c in chunks)  # half a paper never reaches search


async def test_a_timeout_that_is_not_the_deadline_is_an_ordinary_failure(worker_session, sample_pdf):
    class CommandTimeout(FakeEmbedder):
        async def encode(self, texts):
            raise TimeoutError("command timed out")  # e.g. asyncpg's, long before the 20 minutes

    paper = Paper(file_path=str(sample_pdf), title="placeholder")
    worker_session.add(paper)
    await worker_session.commit()

    await ingest.ingest_paper({"embedder": CommandTimeout()}, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error) == ("failed", "TimeoutError: command timed out")


async def test_the_deadline_message_names_the_minutes():
    assert ingest.timed_out(20 * 60) == "Ingesting took longer than 20 minutes; Re-ingest to try again"


async def test_reembed_past_its_deadline_stops_without_failing_the_paper(
    worker_session, sample_pdf, monkeypatch, caplog
):
    paper, slow = await slow_ingest(worker_session, sample_pdf, monkeypatch)
    await ingest.ingest_paper({"embedder": FakeEmbedder()}, str(paper.id))  # setup, under the long deadline
    short_deadline(monkeypatch)
    writes = record_writes(monkeypatch)

    with caplog.at_level("WARNING", logger="app.workers.ingest"):
        await ingest.reembed_paper({"embedder": slow}, str(paper.id))  # returns, doesn't raise
    await worker_session.refresh(paper)

    assert f"re-embedding {paper.id} ran past" in caplog.text  # it was the deadline that stopped it
    assert writes == [1]  # the second slice never landed
    assert (paper.status, paper.status_error) == ("ready", None)
    error = (await embedding_sources.active(worker_session)).error  # what Settings shows beside Try again
    assert error is not None and "took longer than 0 minutes; Try again" in error


async def test_a_reembed_timeout_that_is_not_the_deadline_propagates(worker_session, sample_pdf, monkeypatch):
    class CommandTimeout(FakeEmbedder):
        async def encode(self, texts):
            raise TimeoutError("command timed out")

    paper, _ = await slow_ingest(worker_session, sample_pdf, monkeypatch)
    await ingest.ingest_paper({"embedder": FakeEmbedder()}, str(paper.id))

    with pytest.raises(TimeoutError, match="command timed out"):  # arq sees a real failure
        await ingest.reembed_paper({"embedder": CommandTimeout()}, str(paper.id))


def test_arq_backstop_is_longer_than_the_code_deadline():
    assert IngestWorkerSettings.job_timeout == ingest.INGEST_JOB_TIMEOUT + 60


@pytest.fixture
def pool(monkeypatch) -> FakeArq:
    fake = FakeArq()
    monkeypatch.setattr(queue, "_pool", fake)
    return fake


@pytest.fixture
def one_chunk_a_slice(monkeypatch) -> None:
    monkeypatch.setattr(ingest, "EMBED_WRITE_BATCH", 1)
    monkeypatch.setattr(ingest, "EMBED_SLICE_SECONDS", 0)


async def embedding_paper(session, sample_pdf, count: int) -> Paper:
    paper = await paper_with_chunks(session, count)
    paper.file_path, paper.status = str(sample_pdf), PaperStatus.EMBEDDING
    await session.commit()
    return paper


async def run_queued(pool: FakeArq, job_ctx: dict) -> list[str]:
    """Runs the queued jobs first in, first out, as arq does, including what they queue. The papers, in run order."""
    ran = []
    while pool.jobs:
        name, *args = pool.jobs.pop(0)
        await getattr(ingest, name)(job_ctx, *args)
        ran.append(args[0])
    return ran


@pytest.mark.usefixtures("one_chunk_a_slice")
async def test_a_long_paper_stops_after_a_slice_and_queues_the_rest(worker_session, sample_pdf, embedder, pool):
    paper = Paper(file_path=str(sample_pdf), title="placeholder")
    worker_session.add(paper)
    await worker_session.commit()

    await ingest.ingest_paper({"embedder": embedder}, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == PaperStatus.EMBEDDING
    chunks = await vectors_of(worker_session, paper.id)
    assert sum(c.embedding is not None for c in chunks) == 1 < len(chunks)
    assert pool.jobs == [("embed_rest", str(paper.id))]


@pytest.mark.usefixtures("one_chunk_a_slice")
async def test_embed_rest_finishes_the_paper_without_embedding_a_chunk_twice(
    worker_session, sample_pdf, embedder, pool
):
    paper = Paper(file_path=str(sample_pdf), title="placeholder")
    worker_session.add(paper)
    await worker_session.commit()
    await ingest.ingest_paper({"embedder": embedder}, str(paper.id))

    await run_queued(pool, {"embedder": embedder})
    await worker_session.refresh(paper)

    chunks = await vectors_of(worker_session, paper.id)
    assert (paper.status, paper.status_error) == (PaperStatus.READY, None)
    assert all(c.embedding is not None for c in chunks)
    assert sum(len(texts) for texts, _ in embedder.calls) == len(chunks)


@pytest.mark.usefixtures("one_chunk_a_slice")
async def test_a_short_paper_finishes_between_a_long_papers_slices(worker_session, sample_pdf, embedder, pool):
    long = await embedding_paper(worker_session, sample_pdf, 3)
    short = await embedding_paper(worker_session, sample_pdf, 1)
    pool.jobs.extend([("embed_rest", str(long.id)), ("embed_rest", str(short.id))])

    ran = await run_queued(pool, {"embedder": embedder})

    assert ran == [str(long.id), str(short.id), str(long.id), str(long.id)]


@pytest.mark.usefixtures("one_chunk_a_slice")
async def test_a_killed_worker_resumes_without_repeating_finished_chunks(worker_session, sample_pdf, embedder, pool):
    paper = await embedding_paper(worker_session, sample_pdf, 3)
    await ingest.embed_rest({"embedder": embedder}, str(paper.id))  # one chunk written; then the worker dies
    pool.jobs.clear()
    embedder.calls.clear()

    await ingest.embed_rest({"embedder": embedder, "job_try": 2}, str(paper.id))  # arq runs the job again

    assert sum(len(texts) for texts, _ in embedder.calls) == 1  # the next chunk, not the first again


async def test_embed_rest_stops_quietly_when_the_paper_is_gone_or_not_embedding(
    worker_session, sample_pdf, embedder, pool
):
    paper = await embedding_paper(worker_session, sample_pdf, 2)
    paper.status = PaperStatus.UPLOADED  # a Re-ingest took it back
    await worker_session.commit()

    await ingest.embed_rest({"embedder": embedder}, str(paper.id))
    await ingest.embed_rest({"embedder": embedder}, str(uuid.uuid4()))

    assert embedder.calls == [] and pool.jobs == []


@pytest.mark.usefixtures("one_chunk_a_slice")
async def test_a_failing_source_ends_the_run_without_requeuing(worker_session, sample_pdf, pool):
    paper = await embedding_paper(worker_session, sample_pdf, 2)

    await ingest.embed_rest({"embedder": FakeEmbedder(refuse="Key rejected")}, str(paper.id))
    await worker_session.refresh(paper)

    assert pool.jobs == []
    assert paper.status == PaperStatus.READY  # as ingest does today: ready, with Try again in Settings (D155)
    assert (await embedding_sources.active(worker_session)).error == "Key rejected"


async def test_embed_rest_past_its_deadline_retries_then_fails_cleanly(
    worker_session, sample_pdf, monkeypatch, pool
):
    monkeypatch.setattr(ingest, "EMBED_WRITE_BATCH", 1)
    short_deadline(monkeypatch)
    paper = await embedding_paper(worker_session, sample_pdf, 2)

    with pytest.raises(Retry):
        await ingest.embed_rest({"embedder": HangingEmbedder()}, str(paper.id))
    await worker_session.refresh(paper)
    assert paper.status == PaperStatus.EMBEDDING
    assert sum(c.embedding is not None for c in await vectors_of(worker_session, paper.id)) == 1  # kept for the retry

    await ingest.embed_rest({"embedder": FakeEmbedder(), "job_try": ingest.MAX_TRIES}, str(paper.id))
    await worker_session.refresh(paper)
    assert paper.status == PaperStatus.FAILED
    assert paper.status_error == ingest.INTERRUPTED.format(times=ingest.MAX_TRIES - 1)
    assert all(c.embedding is None for c in await vectors_of(worker_session, paper.id))  # half a paper never answers


async def test_an_unexpected_error_in_embed_rest_fails_the_paper_instead_of_leaving_it_embedding(
    worker_session, sample_pdf, pool
):
    class Broken(FakeEmbedder):
        async def encode(self, texts):
            raise ValueError("boom")

    paper = await embedding_paper(worker_session, sample_pdf, 2)

    await ingest.embed_rest({"embedder": Broken()}, str(paper.id))  # arq wouldn't retry this; the paper must not hang
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error) == (PaperStatus.FAILED, "ValueError: boom")
