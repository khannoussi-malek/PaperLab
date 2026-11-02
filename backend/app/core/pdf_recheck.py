"""R20: the weekly look for a free copy of papers saved without a PDF, with the sources Add uses. A look that met a busy
or unreachable source says nothing about whether a copy exists, so it is tried again soon (RETRY_DELAYS) instead."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import discovery, paper_events, paper_sources, papers, queue
from app.core.errors import Conflict
from app.models import Paper

logger = logging.getLogger(__name__)

RECHECK_CAP = 25  # papers per run, one run a day (05:00, never at startup): a big backlog drains over days
RECHECK_EVERY = timedelta(days=7)
PAUSE = 3.0  # seconds between papers, on top of each source's own pacing
# Seconds before each retry after a temporary failure; after the last the paper waits for the weekly look.
RETRY_DELAYS = (600, 3600, 6 * 3600)
sleep = asyncio.sleep  # tests replace it

Outcome = Literal["found", "none", "temporary", "error", "skipped"]


async def due(session: AsyncSession, now: datetime) -> list[uuid.UUID]:
    """Claims the papers with no PDF not checked in the last week, longest unchecked first (never checked first): their
    checked-at becomes `now` in one transaction, so a second run, even an overlapping one, takes none of them.
    ponytail: a run that dies or is switched off mid-way leaves its unchecked claims waiting a week; fine for a
    politeness cap."""
    query = (
        select(Paper.id)
        .where(
            Paper.file_path.is_(None), (Paper.pdf_checked_at.is_(None)) | (Paper.pdf_checked_at < now - RECHECK_EVERY)
        )
        .order_by(Paper.pdf_checked_at.asc().nulls_first(), Paper.created_at)
        .limit(RECHECK_CAP)
        .with_for_update(skip_locked=True)  # an overlapping run's claims are skipped, not waited for
    )
    ids = list(await session.scalars(query))
    if ids:
        await session.execute(update(Paper).where(Paper.id.in_(ids)).values(pdf_checked_at=now))
    await session.commit()
    return ids


async def _mark(session: AsyncSession, paper_id: uuid.UUID, outcome: Outcome, claimed: bool) -> None:
    """The result, except for a skip (a paper that got a PDF meanwhile keeps its last real result). The time was set if
    `due` claimed it; a look outside the weekly run sets it here."""
    if outcome != "skipped":
        times = {} if claimed else {"pdf_checked_at": func.now()}
        await session.execute(update(Paper).where(Paper.id == paper_id).values(pdf_check_result=outcome, **times))
    await session.commit()


async def recheck(
    session: AsyncSession, providers: discovery.Providers, paper_id: uuid.UUID, claimed: bool = False
) -> Outcome:
    """One paper: finds a free copy and upgrades it in place (ingest queued, then a pdf_found event). One paper's
    failure is logged and recorded as "error"; it never raises."""
    outcome: Outcome = "error"
    try:
        paper = await session.get(Paper, paper_id, populate_existing=True)
        if paper is None or paper.has_pdf:
            outcome = "skipped"
        else:
            data, tried, _ = await discovery.find_pdf(session, providers, discovery.candidate_of(paper))
            if data is None:
                outcome = "temporary" if discovery.temporary_failures(tried) else "none"
            else:
                await papers.attach_pdf(session, paper_id, data, how="imported")
                outcome = "found"  # kept even if the queueing or the event fails: the PDF is attached
                # queued first: a failed event write can't leave it unqueued
                await queue.enqueue("ingest_paper", str(paper_id))
                url = next((t["url"] for t in tried if t["outcome"] == "pdf"), None)
                await paper_events.record(session, paper_id, "pdf_found", {"url": url, "how": "imported"})
    except Conflict as exc:
        # a held arXiv copy can't be resolved by looking again: "none", so it waits the normal week. already_has_pdf
        # is a race: skipped.
        outcome = "none" if str(exc) == discovery.ALREADY_IN_LIBRARY else "skipped"
    except Exception:
        logger.exception("the free-copy re-check of paper %s failed", paper_id)
        await session.rollback()
    try:
        await _mark(session, paper_id, outcome, claimed)
    except Exception:  # the paper keeps its last result; the others still get their turn
        logger.exception("recording the re-check of paper %s failed", paper_id)
        await session.rollback()
    return outcome


async def schedule_retry(session: AsyncSession, paper_id: uuid.UUID, attempt: int = 0) -> bool:
    """Queues look number `attempt` after its delay. False once the retries are spent, or with the re-check off in
    Settings: the switch covers every look nobody asked for."""
    if attempt >= len(RETRY_DELAYS) or not (await paper_sources.get(session)).pdf_recheck_enabled:
        return False
    await queue.enqueue(  # refused when this look is already queued: scheduled either way
        "retry_free_pdf", str(paper_id), attempt, job_id=f"retry_free_pdf:{paper_id}:{attempt}",
        defer_seconds=RETRY_DELAYS[attempt],
    )
    return True


async def run(session: AsyncSession, providers: discovery.Providers, now: datetime) -> dict[str, int]:
    """Re-checks every due paper, PAUSE apart, until Settings turns the re-check off. Counts by outcome."""
    counts = _no_counts()
    for index, paper_id in enumerate(await due(session, now)):
        if index:
            await sleep(PAUSE)
        if not (await paper_sources.get(session)).pdf_recheck_enabled:  # switched off mid-run: the rest wait
            break
        outcome = await recheck(session, providers, paper_id, claimed=True)
        counts[outcome] += 1
        if outcome == "temporary":
            await schedule_retry(session, paper_id)
    return counts


async def run_for(session: AsyncSession, providers: discovery.Providers, paper_ids: list[uuid.UUID]) -> dict[str, int]:
    """Re-checks the papers someone asked about, whatever Settings says about the weekly look. Counts by outcome."""
    counts = _no_counts()
    for index, paper_id in enumerate(paper_ids):
        if index:
            await sleep(PAUSE)
        outcome = await recheck(session, providers, paper_id)
        counts[outcome] += 1
        if outcome == "temporary":
            await schedule_retry(session, paper_id)
    return counts


def _no_counts() -> dict[str, int]:
    return {"found": 0, "none": 0, "temporary": 0, "error": 0, "skipped": 0}
