import logging
import uuid

from app.config import settings
from app.core import discovery, paper_sources, papers, references
from app.core.errors import Conflict
from app.db import SessionLocal
from app.providers import discovery_fake

logger = logging.getLogger(__name__)


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
            await references.embed_new(session, ctx["embedder"])
            await references.set_state(session, pid, "ready", " ".join(notices) or None)
        except Conflict as exc:
            await session.rollback()
            await references.set_state(session, pid, "failed", str(exc))
        except Exception:
            logger.exception("fetching references failed for %s", pid)
            await session.rollback()
            await references.set_state(session, pid, "failed", references.FETCH_FAILED)
