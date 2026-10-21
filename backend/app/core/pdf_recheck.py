"""R20: the weekly look for a free copy of papers saved without a PDF, with the sources Add uses."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import discovery, paper_events, papers, queue
from app.core.errors import Conflict
from app.models import Paper

logger = logging.getLogger(__name__)

RECHECK_CAP = 25  # papers per run: a big backlog drains over days
RECHECK_EVERY = timedelta(days=7)
PAUSE = 3.0  # seconds between papers, on top of each source's own pacing
sleep = asyncio.sleep  # tests replace it

Outcome = Literal["found", "none", "error", "skipped"]


async def due(session: AsyncSession, now: datetime) -> list[uuid.UUID]:
    """Papers with no PDF not checked in the last week, longest unchecked first (never checked first)."""
    query = (
        select(Paper.id)
        .where(
            Paper.file_path.is_(None), (Paper.pdf_checked_at.is_(None)) | (Paper.pdf_checked_at < now - RECHECK_EVERY)
        )
        .order_by(Paper.pdf_checked_at.asc().nulls_first(), Paper.created_at)
        .limit(RECHECK_CAP)
    )
    return list(await session.scalars(query))


async def _mark(session: AsyncSession, paper_id: uuid.UUID, now: datetime, outcome: Outcome) -> None:
    """Always the time; the result too, except for a skip (a paper that has a PDF or is held elsewhere keeps its
    last real result)."""
    values: dict = {"pdf_checked_at": now}
    if outcome != "skipped":
        values["pdf_check_result"] = outcome
    await session.execute(update(Paper).where(Paper.id == paper_id).values(**values))
    await session.commit()


async def recheck(session: AsyncSession, providers: discovery.Providers, paper_id: uuid.UUID, now: datetime) -> Outcome:
    """One paper: finds a free copy and upgrades it in place (ingest queued, a pdf_found event). One paper's failure is
    logged and recorded as "error"; it never raises."""
    outcome: Outcome = "error"
    try:
        paper = await session.get(Paper, paper_id, populate_existing=True)
        if paper is None or paper.has_pdf:
            outcome = "skipped"
        else:
            data, tried, _ = await discovery.find_pdf(session, providers, discovery.candidate_of(paper))
            if data is None:
                outcome = "none"
            else:
                await papers.attach_pdf(session, paper_id, data, how="imported")
                outcome = "found"  # kept even if the event or the queueing fails: the PDF is attached
                url = next((t["url"] for t in tried if t["outcome"] == "pdf"), None)
                await paper_events.record(session, paper_id, "pdf_found", {"url": url, "how": "imported"})
                await queue.enqueue("ingest_paper", str(paper_id))
    except Conflict:  # already_in_library (a held arXiv copy) or already_has_pdf (a race)
        outcome = "skipped"
    except Exception:
        logger.exception("the free-copy re-check of paper %s failed", paper_id)
        await session.rollback()
    try:
        await _mark(session, paper_id, now, outcome)
    except Exception:  # the paper is checked again next run; the others still get their turn
        logger.exception("recording the re-check of paper %s failed", paper_id)
        await session.rollback()
    return outcome


async def run(session: AsyncSession, providers: discovery.Providers, now: datetime) -> dict[str, int]:
    """Re-checks every due paper, PAUSE apart. Counts by outcome."""
    counts = {"found": 0, "none": 0, "error": 0, "skipped": 0}
    for index, paper_id in enumerate(await due(session, now)):
        if index:
            await sleep(PAUSE)
        counts[await recheck(session, providers, paper_id, now)] += 1
    return counts
