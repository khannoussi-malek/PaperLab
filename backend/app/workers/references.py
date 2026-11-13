import logging
import uuid

from app.config import settings
from app.core import discovery, paper_sources, papers, references
from app.core.errors import Conflict
from app.db import SessionLocal
from app.providers import discovery_fake
from app.providers.base import LLMError, LLMUnavailable
from app.workers.ingest import search_embedder

logger = logging.getLogger(__name__)


EMBED_NOTE_JOB_TIMEOUT = 5 * 60


async def embed_note(ctx: dict, note_id: str) -> None:
    """Embeds one note as it is saved, so a fetch ranks references by it without waiting for the next fetch. Quiet
    when no search model can embed it (none set up, or the source refuses): the fetch-time catch-up embeds it later."""
    nid = uuid.UUID(note_id)
    async with SessionLocal() as session:
        try:
            embedder = await search_embedder(ctx, session)
            if embedder is None:
                logger.info("note %s wasn't embedded on save: no search model", nid)
                return
            await references.embed_notes(session, embedder, [nid])
        except (LLMUnavailable, LLMError) as exc:
            logger.info("note %s wasn't embedded on save, the next references fetch will: %s", nid, exc)


async def fetch_references(ctx: dict, paper_id: str) -> None:
    """Fetches, stores and embeds a paper's references and citing works. Never fails the paper: a failure only sets
    `references_state` to failed with a message the tab shows. ctx["transport"] is a test's MockTransport."""
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        try:
            paper = await papers.get_paper(session, pid)
            sources = await paper_sources.get(session)
            transport = ctx.get("transport")
            if transport is None and settings.discovery_provider == "fake":
                transport = discovery_fake.transport()
            providers = discovery.build_providers(sources, transport)
            try:
                notices = await references.fetch(session, providers, paper)
            finally:
                await providers.aclose()
            try:
                await references.embed_new(session, await search_embedder(ctx, session))
            except (LLMUnavailable, LLMError) as exc:
                # No paper lacks vectors because of it, so no source_error (D155): the tab ranks without note
                # similarity until the next fetch embeds them.
                logger.warning(
                    "the references of %s weren't embedded, so the tab ranks without note similarity: %s", pid, exc
                )
            await references.set_state(session, pid, "ready", " ".join(notices) or None)
        except Conflict as exc:
            await session.rollback()
            await references.set_state(session, pid, "failed", str(exc))
        except Exception:
            logger.exception("fetching references failed for %s", pid)
            await session.rollback()
            await references.set_state(session, pid, "failed", references.FETCH_FAILED)
