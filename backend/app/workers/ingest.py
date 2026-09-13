import asyncio
import logging
import uuid

from app.core import papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import PaperStatus
from app.providers import embedding
from app.providers.extraction import extract

logger = logging.getLogger(__name__)


async def ingest_paper(ctx: dict, paper_id: str) -> None:
    """uploaded -> extracting -> chunking -> embedding -> ready, or failed with status_error.

    Idempotent: chunks and their vectors are replaced wholesale, so re-run it freely while tuning chunking.
    ctx["embedder"] is the model WorkerSettings.on_startup loaded. The enriching stage lands in M6.5.
    """
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        paper = await papers.get_paper(session, pid)
        try:
            await papers.set_status(session, pid, PaperStatus.EXTRACTING)
            doc = await asyncio.to_thread(extract, paper.file_path)

            # Enriched metadata beats the font heuristic; don't overwrite it on re-runs.
            title = {"title": doc.title} if doc.title and paper.openalex_id is None else {}
            await papers.set_status(session, pid, PaperStatus.CHUNKING, page_count=doc.page_count, **title)
            drafts = chunk_blocks(doc.blocks)
            await papers.replace_chunks(session, pid, drafts)

            await papers.set_status(session, pid, PaperStatus.EMBEDDING)
            chunks = await papers.list_chunks(session, pid)
            vectors = await embedding.embed_documents(ctx["embedder"], [c.text for c in chunks])
            await papers.set_embeddings(session, [c.id for c in chunks], vectors)

            await papers.set_status(session, pid, PaperStatus.READY)
            logger.info("ingested %s: %d pages, %d chunks", pid, doc.page_count, len(drafts))
        except Exception as exc:
            logger.exception("ingest failed for %s", pid)
            await session.rollback()
            await papers.set_status(session, pid, PaperStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
