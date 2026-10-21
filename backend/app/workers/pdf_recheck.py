"""ARQ cron: recheck_free_pdfs (R20), the weekly look for a free copy of papers saved without a PDF."""

import logging
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
