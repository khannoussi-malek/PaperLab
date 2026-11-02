"""ARQ jobs for free copies of papers saved without a PDF: recheck_free_pdfs (R20), the weekly cron; retry_free_pdf, the
look again after a busy source; recheck_papers, a batch someone asked for."""

import logging
import uuid
from datetime import datetime, timezone

from app.core import discovery, paper_sources, pdf_recheck
from app.db import SessionLocal

logger = logging.getLogger(__name__)

RECHECK_JOB_TIMEOUT = 3600


async def recheck_free_pdfs(ctx: dict) -> dict[str, int] | str:
    """Does nothing while Settings → Paper sources has the re-check off. Fake providers come from
    DISCOVERY_PROVIDER=fake, as for every request."""
    async with SessionLocal() as session:
        if not (await paper_sources.get(session)).pdf_recheck_enabled:
            return "disabled"
        async with discovery.open_providers(session) as providers:
            counts = await pdf_recheck.run(session, providers, datetime.now(timezone.utc))
    logger.info("recheck_free_pdfs: %s", counts)
    return counts


async def retry_free_pdf(ctx: dict, paper_id: str, attempt: int) -> str:
    """One more look after a temporary failure; still temporary, the next is queued. `attempt` is this look's number."""
    pid = uuid.UUID(paper_id)
    async with SessionLocal() as session:
        if not (await paper_sources.get(session)).pdf_recheck_enabled:
            return "disabled"
        async with discovery.open_providers(session) as providers:
            outcome = await pdf_recheck.recheck(session, providers, pid)
        if outcome == "temporary":
            await pdf_recheck.schedule_retry(session, pid, attempt + 1)
    logger.info("retry_free_pdf %s, attempt %d: %s", paper_id, attempt, outcome)
    return outcome


async def recheck_papers(ctx: dict, paper_ids: list[str]) -> dict[str, int]:
    async with SessionLocal() as session:
        async with discovery.open_providers(session) as providers:
            counts = await pdf_recheck.run_for(session, providers, [uuid.UUID(p) for p in paper_ids])
    logger.info("recheck_papers: %s", counts)
    return counts
