import asyncio
import logging
import uuid

from app.core import enrichment, paper_sources, papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import PaperStatus
from app.providers import embedding, openalex
from app.providers.extraction import ExtractedDoc, extract

logger = logging.getLogger(__name__)


async def _enrich(session, transport, paper_id: uuid.UUID, doc: ExtractedDoc) -> None:
    """Asks OpenAlex only while it is on in Settings → Paper sources, read here so a change applies to the next ingest
    without a restart (P5). Never fatal (addendum §6d): on any error the paper keeps whatever was saved before the
    error and still reaches ready."""
    try:
        hints = enrichment.pdf_hints(doc.first_page_text, doc.metadata)
        sources = await paper_sources.get(session)
        if not sources.enabled["openalex"]:
            await enrichment.enrich_paper(session, None, paper_id, hints)
            return
        key = sources.api_keys["openalex"]
        async with openalex.new_client(sources.contact_email, transport, api_key=key) as http:
            await enrichment.enrich_paper(session, http, paper_id, hints)
    except Exception:
        logger.exception("enrichment failed for %s; the paper stays usable", paper_id)
        await session.rollback()


async def search_embedder(ctx: dict):
    """The model that embeds chunks: a test's fake in ctx["embedder"], else this process's own, loaded on first need
    and kept (D136). None while no search model is downloaded."""
    if "embedder" in ctx:
        return ctx["embedder"]
    return await asyncio.to_thread(embedding.get_model)


async def ingest_paper(ctx: dict, paper_id: str) -> None:
    """uploaded -> extracting -> chunking -> embedding -> enriching -> ready, or failed with status_error.

    Idempotent: chunks, vectors, authorships and topics are replaced wholesale, so re-run it freely. With no search
    model the embedding stage is skipped: the paper is ready to read and note, and a finished download embeds it (D137).
    Tests put a fake model in ctx["embedder"] and an httpx transport in ctx["transport"].
    """
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        paper = await papers.get_paper(session, pid)
        try:
            await papers.set_status(session, pid, PaperStatus.EXTRACTING)
            doc = await asyncio.to_thread(extract, paper.file_path)
            # extract() can take seconds; re-read the lock right before deciding, in case a PATCH landed meanwhile.
            await session.refresh(paper, ["openalex_id", "manual_fields"])

            # Enriched or corrected titles beat the font heuristic; don't overwrite them on re-runs.
            keep = paper.openalex_id is not None or "title" in paper.manual_fields
            title = {"title": doc.title} if doc.title and not keep else {}
            await papers.set_status(session, pid, PaperStatus.CHUNKING, page_count=doc.page_count, **title)
            drafts = chunk_blocks(doc.blocks)
            await papers.replace_chunks(session, pid, drafts)

            embedder = await search_embedder(ctx)
            if embedder is None:
                logger.info("no search model: %s is ready without vectors", pid)
            else:
                await papers.set_status(session, pid, PaperStatus.EMBEDDING)
                chunks = await papers.list_chunks(session, pid)
                vectors = await embedding.embed_documents(embedder, [c.text for c in chunks])
                await papers.set_embeddings(session, [c.id for c in chunks], vectors)

            await papers.set_status(session, pid, PaperStatus.ENRICHING)
            await _enrich(session, ctx.get("transport"), pid, doc)
            # Don't read paper's ORM attributes past this point: _enrich's rollback (on the failure path) expires
            # them, and an async lazy load outside an awaited call raises MissingGreenlet, not a clean re-fetch.

            await papers.set_status(session, pid, PaperStatus.READY)
            logger.info("ingested %s: %d pages, %d chunks", pid, doc.page_count, len(drafts))
        except Exception as exc:
            logger.exception("ingest failed for %s", pid)
            await session.rollback()
            await papers.set_status(session, pid, PaperStatus.FAILED, error=f"{type(exc).__name__}: {exc}")


async def reembed_paper(ctx: dict, paper_id: str) -> None:
    """Embeds a paper's chunks again with the configured model, in place: chunk ids stay, so saved answers and notes
    keep their sources. A library re-index queues one per paper, and so does a finished model download for each paper
    without vectors (D137). With no search model it does nothing."""
    pid = uuid.UUID(paper_id)
    embedder = await search_embedder(ctx)
    if embedder is None:
        logger.info("no search model: re-embedding %s skipped", pid)
        return
    async with SessionLocal() as session:
        chunks = await papers.list_chunks(session, pid)
        vectors = await embedding.embed_documents(embedder, [c.text for c in chunks])
        await papers.set_embeddings(session, [c.id for c in chunks], vectors)
    logger.info("re-embedded %s: %d chunks", pid, len(chunks))
