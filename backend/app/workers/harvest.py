"""Periodic metadata harvesting for sources with no live search API (M32 batch 6 phase A: IACR ePrint
only; a later phase adds bioRxiv/medRxiv onto this same infrastructure). Each harvest source gets one
HarvestCursor row tracking its own last-synced point, and one ARQ cron job (registered in
workers/settings.py) that pages through everything new since then and upserts it into external_refs --
the same generic store every live source's own candidates already land in.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.candidates import Candidate, from_iacr_eprint
from app.db import SessionLocal
from app.models import ExternalRef
from app.models.harvest import HarvestCursor
from app.providers import iacr_eprint

logger = logging.getLogger(__name__)

# ARQ's own default job_timeout is 300s; a first-ever harvest can page through roughly 57 pages of 500
# (confirmed live: IACR's own full archive is 28,110 records) -- generous, matching
# workers/workspace_search.py's own SEARCH_RUN_JOB_TIMEOUT precedent for a similarly long-running job.
HARVEST_JOB_TIMEOUT = 1800
# Bounds one job run's own page count, the same backstop shape SEARCH_RUN's own MAX_BATCH_ITERATIONS
# uses -- a first-ever harvest needs ~57 pages; 200 leaves headroom without looping forever on a bug.
MAX_HARVEST_PAGES = 200


async def harvest_ingest_candidate(session: AsyncSession, candidate: Candidate) -> None:
    """Find this harvest source's own existing row by its own external_ids key, or create one. Not
    workspace_search.py's own _find_or_create_external_ref -- that function resolves conflicts between
    several different LIVE sources' own concurrent results for the SAME query, a different problem from
    recording one periodic source's own harvested finding."""
    source, eprint_id = next(iter(candidate.external_ids.items()))
    existing = (
        await session.execute(select(ExternalRef).where(ExternalRef.external_ids[source].astext == eprint_id))
    ).scalar_one_or_none()
    if existing is not None:
        existing.title = candidate.title
        existing.authors = candidate.authors
        existing.abstract = candidate.abstract
        existing.year = candidate.year
        return
    session.add(
        ExternalRef(
            title=candidate.title, authors=candidate.authors, year=candidate.year, abstract=candidate.abstract,
            external_ids=dict(candidate.external_ids), sources=list(candidate.sources),
        )
    )


async def _sync_iacr_eprint(session: AsyncSession) -> None:
    cursor = await session.get(HarvestCursor, "iacr_eprint")
    if cursor is None:
        cursor = HarvestCursor(source="iacr_eprint", last_synced_at=None)
        session.add(cursor)
    from_date = cursor.last_synced_at.strftime("%Y-%m-%d") if cursor.last_synced_at else "1996-01-01"
    until_date = datetime.now(UTC).strftime("%Y-%m-%d")

    http = iacr_eprint.new_client()
    try:
        token: str | None = None
        for _ in range(MAX_HARVEST_PAGES):
            entries, token = (
                await iacr_eprint.fetch_page(http, resumption_token=token)
                if token
                else await iacr_eprint.fetch_page(http, from_date=from_date, until_date=until_date)
            )
            for entry in entries:
                await harvest_ingest_candidate(session, from_iacr_eprint(entry))
            await session.flush()
            if token is None:
                break
        else:
            # The loop exhausted its page budget with more pages still pending -- raise rather than
            # silently truncate the harvest; harvest_iacr_eprint's own except/rollback then keeps the
            # cursor from advancing, so the next run resumes from the last successfully-finished point
            # instead of losing the un-fetched remainder.
            raise RuntimeError(
                f"IACR ePrint harvest hit MAX_HARVEST_PAGES ({MAX_HARVEST_PAGES}) with more pages pending"
            )
    finally:
        await http.aclose()

    cursor.last_synced_at = datetime.strptime(until_date, "%Y-%m-%d").replace(tzinfo=UTC)


async def harvest_iacr_eprint(ctx: dict) -> None:
    async with SessionLocal() as session:
        try:
            await _sync_iacr_eprint(session)
            await session.commit()
        except Exception:
            logger.exception("IACR ePrint harvest failed")
            await session.rollback()
            raise
