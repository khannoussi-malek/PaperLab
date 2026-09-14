import asyncio
import logging
import uuid

from app.core import enrichment, papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import PaperStatus
from app.providers import embedding
from app.providers.extraction import ExtractedDoc, extract

logger = logging.getLogger(__name__)


async def _enrich(session, http, paper_id: uuid.UUID, doc: ExtractedDoc) -> None:
    """Never fatal (addendum §6d): on any error the paper keeps what extraction gave it and still reaches ready."""
    try:
        await enrichment.enrich_paper(session, http, paper_id, enrichment.pdf_hints(doc.first_page_text, doc.metadata))
    except Exception:
        logger.exception("enrichment failed for %s; the paper stays usable", paper_id)
        await session.rollback()


async def ingest_paper(ctx: dict, paper_id: str) -> None:
    """uploaded -> extracting -> chunking -> embedding -> enriching -> ready, or failed with status_error.

    Idempotent: chunks, vectors, authorships and topics are replaced wholesale, so re-run it freely.
    ctx["embedder"] is the model WorkerSettings.on_startup loaded; ctx["openalex"] its OpenAlex client, or None.
    """
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        paper = await papers.get_paper(session, pid)
        try:
            await papers.set_status(session, pid, PaperStatus.EXTRACTING)
            doc = await asyncio.to_thread(extract, paper.file_path)

            # Enriched or corrected titles beat the font heuristic; don't overwrite them on re-runs.
            keep = paper.openalex_id is not None or "title" in paper.manual_fields
            title = {"title": doc.title} if doc.title and not keep else {}
            await papers.set_status(session, pid, PaperStatus.CHUNKING, page_count=doc.page_count, **title)
            drafts = chunk_blocks(doc.blocks)
            await papers.replace_chunks(session, pid, drafts)

            await papers.set_status(session, pid, PaperStatus.EMBEDDING)
            chunks = await papers.list_chunks(session, pid)
            vectors = await embedding.embed_documents(ctx["embedder"], [c.text for c in chunks])
            await papers.set_embeddings(session, [c.id for c in chunks], vectors)

            await papers.set_status(session, pid, PaperStatus.ENRICHING)
            await _enrich(session, ctx.get("openalex"), pid, doc)

            await papers.set_status(session, pid, PaperStatus.READY)
            logger.info("ingested %s: %d pages, %d chunks", pid, doc.page_count, len(drafts))
        except Exception as exc:
            logger.exception("ingest failed for %s", pid)
            await session.rollback()
            await papers.set_status(session, pid, PaperStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
