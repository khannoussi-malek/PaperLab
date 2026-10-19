import asyncio
import logging
import time
import uuid
from contextlib import AsyncExitStack

from sqlalchemy import update

from app.core import embedding_index, embedding_sources, enrichment, merges, paper_sources, papers
from app.core.candidates import Candidate
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import Chunk, Paper, PaperStatus
from app.providers import crossref, embedding, openalex
from app.providers.base import LLMError, LLMUnavailable
from app.providers.extraction import ExtractedDoc, extract

logger = logging.getLogger(__name__)

# arq's own default, set on IngestWorkerSettings so the two can't drift. arq never runs a job past it, so the last try
# ends the paper failed instead of starting again: a paper that stops the worker every time would otherwise sit
# mid-ingest forever, as 67 did when ten ingests at once ran the worker out of memory (2026-10-13).
MAX_TRIES = 5
EMBED_WRITE_BATCH = 64  # chunks per encode and per write
# Enforced inside the job, not by arq: arq's cancel is a CancelledError, which `except Exception` doesn't catch, so
# the paper would sit at "embedding" forever. This deadline ends it failed, with the copy below and no partial
# vectors. Neither can stop a thread already running (extract, an encode), so arq only gets a longer backstop
# (settings.py).
INGEST_JOB_TIMEOUT = 20 * 60
INTERRUPTED = (
    "Ingesting stopped before it finished {times} times (the worker restarted or ran out of memory). "
    "Re-ingest to try again."
)


def timed_out(seconds: float) -> str:
    return f"Ingesting took longer than {int(seconds // 60)} minutes; Re-ingest to try again"


def _timings(pid: uuid.UUID, marks: list[tuple[str, float]], started: float, chunks: int, pages: int) -> str:
    """One line with how long each stage ran, for the stages reached so far (a stage not reached shows 0.0s)."""
    now = time.monotonic()
    ends = [at for _, at in marks[1:]] + [now]
    took = {name: end - at for (name, at), end in zip(marks, ends, strict=True)}
    stages = " ".join(f"{n}={took.get(n, 0.0):.1f}s" for n in ("extracting", "chunking", "embedding", "enriching"))
    return f"ingest timings for {pid}: {stages} total={now - started:.1f}s chunks={chunks} pages={pages}"


async def _enrich(session, transport, paper_id: uuid.UUID, doc: ExtractedDoc) -> list[enrichment.Collision]:
    """Asks OpenAlex only while it is on in Settings → Paper sources, read here so a change applies to the next ingest
    without a restart (P5). Never fatal (addendum §6d): on any error the paper keeps whatever was saved before the
    error and still reaches ready. Returns the identifiers other papers hold (none after an error)."""
    try:
        hints = enrichment.pdf_hints(doc.first_page_text, doc.metadata)
        sources = await paper_sources.get(session)
        async with AsyncExitStack() as stack:
            http = cr = None
            if sources.enabled["openalex"]:
                key = sources.api_keys["openalex"]
                http = await stack.enter_async_context(
                    openalex.new_client(email=sources.contact_email, transport=transport, api_key=key)
                )
            # One polite-pool Crossref request at most, shared by the source type and the citation fields (volume,
            # issue, pages, editors), and skipped when OpenAlex already filled everything Crossref could add.
            if sources.enabled["crossref"]:
                cr = await stack.enter_async_context(
                    crossref.new_client(email=sources.contact_email, transport=transport)
                )
            return await enrichment.enrich_paper(session, http, paper_id, hints, crossref_http=cr)
    except Exception:
        logger.exception("enrichment failed for %s; the paper stays usable", paper_id)
        await session.rollback()
        return []


async def _merge_after_ingest(pid: uuid.UUID, collisions: list[enrichment.Collision], evidence: Candidate) -> None:
    """R17, in a session of its own: never fails the ingest. merge rolls back on a failure, so both papers stay, and
    a fresh session records the failure, best effort."""
    try:
        async with SessionLocal() as session:
            await merges.after_ingest(session, pid, collisions, evidence)
    except Exception as exc:
        logger.exception("merging %s after ingest failed; both papers stay as they were", pid)
        try:
            async with SessionLocal() as session:
                await merges.report_failure(session, pid, collisions, exc)
        except Exception:
            logger.exception("recording the failed merge of %s failed too", pid)


async def search_embedder(ctx: dict, session):
    """The embedder for this job: a test's fake in ctx["embedder"], else the active search source's, read now so a
    switch applies to the next job without a restart (D151). ctx["transport"] is a test's MockTransport. None while
    Built-in is the source and its model isn't downloaded (D136)."""
    if "embedder" in ctx:
        return ctx["embedder"]
    source = await embedding_sources.active(session)
    return await asyncio.to_thread(embedding.build, source, ctx.get("transport"))


async def _embed(session, pid: uuid.UUID, embedder) -> bool:
    """Embeds the paper's chunks in slices of EMBED_WRITE_BATCH, writing each as it is done and only while `embedder`
    is still the search source. A slice is the most a thread left running after a deadline can still do, and the
    progress anyone can see; the vectors written so far stay. A failing source never fails a paper: the old vectors
    stay and the error is kept for Settings' Try again (D155). True when all were written."""
    chunks = await papers.list_chunks(session, pid)
    for start in range(0, len(chunks), EMBED_WRITE_BATCH):
        batch = chunks[start : start + EMBED_WRITE_BATCH]
        try:
            vectors = await embedding.embed_documents(embedder, [c.text for c in batch])
        except (LLMUnavailable, LLMError) as exc:
            logger.warning("embedding %s with %s failed: %s", pid, embedder.label, exc)
            await embedding_sources.record_error(session, str(exc))
            return False
        # ponytail: a switch landing between this check and the commit leaves one slice on the old source; Try again
        # fixes it.
        if await embedding_sources.active_name(session) != embedder.name:
            logger.info("the search source changed while embedding %s; the newer job embeds it", pid)
            return False
        await papers.set_embeddings(session, [c.id for c in batch], vectors, embedder.name)
    return True


async def ingest_paper(ctx: dict, paper_id: str) -> None:
    """uploaded -> extracting -> chunking -> embedding -> enriching -> ready, or failed with status_error.

    Idempotent: chunks, vectors, authorships and topics are replaced wholesale, so re-run it freely. With no search
    model the embedding stage is skipped: the paper is ready to read and note, and a finished download embeds it (D137).
    A failing search source leaves the paper ready without vectors (D155). Tests put a fake model in
    ctx["embedder"] and an httpx transport in ctx["transport"].
    """
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        if (await papers.get_paper(session, pid)).file_path is None:  # extract(None) would "succeed" and wipe chunks
            logger.info("ingest of %s skipped: the paper has no PDF", pid)
            return
    if ctx.get("job_try", 1) >= MAX_TRIES:
        async with SessionLocal() as session:
            await papers.set_status(session, pid, PaperStatus.FAILED, error=INTERRUPTED.format(times=MAX_TRIES - 1))
        logger.warning("ingest of %s stopped %d times; marked failed", pid, MAX_TRIES - 1)
        return
    async with SessionLocal() as session:
        paper = await papers.get_paper(session, pid)
        started = time.monotonic()
        marks: list[tuple[str, float]] = [("extracting", started)]  # each stage's start; a stage runs until the next
        chunks = pages = 0
        collisions: list[enrichment.Collision] = []  # set only once the paper is ready
        evidence = Candidate("")  # what the PDF itself says, for the merge (R15c); set once extracted
        deadline = asyncio.timeout(INGEST_JOB_TIMEOUT)
        try:
            async with deadline:
                await papers.set_status(session, pid, PaperStatus.EXTRACTING)
                doc = await asyncio.to_thread(extract, paper.file_path)
                evidence = merges.pdf_evidence(doc.title, doc.metadata)  # before enrichment, whatever the title lock
                # extract() can take seconds; re-read the lock right before deciding, in case a PATCH landed meanwhile.
                await session.refresh(paper, ["openalex_id", "manual_fields"])

                # Enriched or corrected titles beat the font heuristic; don't overwrite them on re-runs.
                keep = paper.openalex_id is not None or "title" in paper.manual_fields
                title = {"title": doc.title} if doc.title and not keep else {}
                marks.append(("chunking", time.monotonic()))
                pages = doc.page_count
                await papers.set_status(session, pid, PaperStatus.CHUNKING, page_count=doc.page_count, **title)
                drafts = chunk_blocks(doc.blocks)
                await papers.replace_chunks(session, pid, drafts)
                chunks = len(drafts)

                embedder = await search_embedder(ctx, session)
                if embedder is None:
                    logger.info("no search model: %s is ready without vectors", pid)
                else:
                    marks.append(("embedding", time.monotonic()))
                    await papers.set_status(session, pid, PaperStatus.EMBEDDING)
                    await _embed(session, pid, embedder)

                marks.append(("enriching", time.monotonic()))
                await papers.set_status(session, pid, PaperStatus.ENRICHING)
                found = await _enrich(session, ctx.get("transport"), pid, doc)
                # Don't read paper's ORM attributes past this point: _enrich's rollback (on the failure path) expires
                # them, and an async lazy load outside an awaited call raises MissingGreenlet, not a clean re-fetch.

                await papers.set_status(session, pid, PaperStatus.READY)
                collisions = found
                logger.info("ingested %s: %d pages, %d chunks", pid, doc.page_count, len(drafts))
        except Exception as exc:
            await session.rollback()
            # Only the deadline's own timeout, not another one (a database command's, say).
            if isinstance(exc, TimeoutError) and deadline.expired():
                logger.warning("ingest of %s ran past %d s and was stopped", pid, INGEST_JOB_TIMEOUT)
                # Search doesn't look at status, so on a deadline the slices already written are cleared: they must not
                # answer for half a paper. (An embed error mid-ingest and a re-embed timeout leave earlier slices.)
                await session.execute(update(Chunk).where(Chunk.paper_id == pid).values(embedding=None))
                error = timed_out(INGEST_JOB_TIMEOUT)
            else:
                logger.exception("ingest failed for %s", pid)
                error = f"{type(exc).__name__}: {exc}"
            await papers.set_status(session, pid, PaperStatus.FAILED, error=error)
        finally:  # the success, timeout and failure paths all say where the time went
            logger.info(_timings(pid, marks, started, chunks, pages))
    # The very last step: ingest queues no job for the paper, so nothing of ingest's finds M gone after a merge.
    if collisions:
        await _merge_after_ingest(pid, collisions, evidence)


async def index_abstract(ctx: dict, paper_id: str) -> None:
    """embedding -> ready for a paper saved without a PDF (R3): embeds its abstract chunk with the search source, as
    ingest's embedding stage does. Like ingest it always ends ready: with no search model, or a source that fails, the
    paper is ready without vectors and Settings' Try again embeds it (D155). A paper deleted meanwhile, or one that got
    a PDF (ingest owns it now), is left alone."""
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        paper = await session.get(Paper, pid)
        if paper is None or paper.file_path is not None:
            logger.info("indexing the abstract of %s skipped: the paper is gone or has a PDF", pid)
            return
        try:
            embedder = await search_embedder(ctx, session)
            if embedder is None:
                logger.info("no search model: %s is ready without vectors", pid)
            else:
                await _embed(session, pid, embedder)
        except Exception:
            logger.exception("embedding the abstract of %s failed; the paper stays usable", pid)
        finally:  # also when arq cancels the job at job_timeout (not an Exception), which still propagates
            await session.rollback()  # a no-op after _embed's commits; clears a statement cut short
            # Only while it still has no PDF: one attached meanwhile (R10) is ingest's, never marked ready mid-ingest.
            ready = update(Paper).where(Paper.id == pid, Paper.file_path.is_(None))
            await session.execute(ready.values(status=PaperStatus.READY, status_error=None))
            await session.commit()


async def reembed_paper(ctx: dict, paper_id: str, missing_only: bool = False) -> None:
    """Embeds a paper's chunks again with the search source, in place: chunk ids stay, so saved answers and notes keep
    their sources. A re-index queues one per paper; a switch and Try again queue them with missing_only, which skips a
    paper already on the source, so a double click or an earlier queued job never pays a cloud twice (D155). A
    finished model download queues one per paper without vectors (D137). With no search model it does nothing."""
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        embedder = await search_embedder(ctx, session)
        if embedder is None:
            logger.info("no search model: re-embedding %s skipped", pid)
            return
        if missing_only and not await embedding_index.papers_to_embed(session, embedder.name, [pid]):
            logger.info("%s is already embedded with %s", pid, embedder.name)
            return
        deadline = asyncio.timeout(INGEST_JOB_TIMEOUT)
        try:
            async with deadline:
                embedded = await _embed(session, pid, embedder)
        except TimeoutError:
            if not deadline.expired():  # another timeout (a database command's): arq must see a real failure
                raise
            await session.rollback()
            logger.warning("re-embedding %s ran past %d s and was stopped", pid, INGEST_JOB_TIMEOUT)
            paper = await papers.get_paper(session, pid)
            minutes = int(INGEST_JOB_TIMEOUT // 60)
            # The paper stays pending in a rebuild; this is what puts Try again in Settings.
            await embedding_sources.record_error(
                session, f"Embedding {paper.title or pid} took longer than {minutes} minutes; Try again"
            )
            return
        if embedded:
            logger.info("re-embedded %s with %s", pid, embedder.name)
