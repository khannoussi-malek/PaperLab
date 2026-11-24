"""The jobs that add section headers to an already-ingested paper's chunks and re-embed them, paced."""

import asyncio
import uuid

from app.core.papers import embedding_index, embedding_sources
from app.core.platform import queue
from app.db import SessionLocal
from app.workers.ingest import INGEST_JOB_TIMEOUT, _embed, logger, search_embedder

# Chunks a second the header re-embeds are spread at: under half the built-in model's measured rate in the worker
# (about 5 a second, 2026-11-23), so the one ingest worker stays mostly free and an upload never waits behind them.
HEADER_PACE = 2.0


async def add_chunk_headers(ctx: dict, paper_id: str) -> None:
    """Re-embeds the paper's chunks embedded before chunk headers, and only those: a paper cut short by the deadline
    resumes where it stopped (each slice commits), and one deleted since it was queued has none left. Nothing when the
    search source is no longer local: a cloud one would bill it."""
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        embedder = await search_embedder(ctx, session)
        if embedder is None or not embedder.is_local:
            return
        deadline = asyncio.timeout(INGEST_JOB_TIMEOUT)
        try:
            async with deadline:
                await _embed(session, pid, embedder, headers_only=True)
        except TimeoutError:
            if not deadline.expired():
                raise
            await session.rollback()
            logger.warning("adding chunk headers to %s ran past %d s; the next start goes on", pid, INGEST_JOB_TIMEOUT)


async def queue_chunk_headers(ctx: dict) -> None:
    """A starting ingest worker queues a re-embed of each paper embedded before chunk headers (0082), once: the job id
    keeps a restart from queueing it twice. Search keeps answering from the old vectors meanwhile (a re-embed with the
    same model is no rebuild, D156). Only for a local search source: a cloud one would bill the whole library again,
    so there only new papers get headers, and Settings' Re-index does the rest when the reader chooses."""
    async with SessionLocal() as session:
        if not (await embedding_sources.active(session)).is_local:
            return
        pending = await embedding_index.papers_without_headers(session)
    start = 0.0
    for paper_id, chunks in pending:
        job_id = f"chunk-headers:{paper_id}"
        await queue.enqueue("add_chunk_headers", str(paper_id), job_id=job_id, defer_seconds=start or None)
        start += chunks / HEADER_PACE
    if pending:
        logger.info("queued %d papers to re-embed with chunk headers over %.0f minutes", len(pending), start / 60)
