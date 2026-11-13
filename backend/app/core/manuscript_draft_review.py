"""The whole-draft reviewer's runs (S2P B7): assemble the paper from the saved .tex files, capture it on a row and queue
one job. The job reads only the row. A response holds ids, severities, summaries, the author's own quotes and close
criteria, never wording for their text (D118). Patterns as core/manuscript_section_review.py."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import draft_review, llm_connections, manuscripts, queue
from app.core.draft_review_issues import MAX_TOTAL_CHARS, MIN_PAPER_CHARS, assemble, split_parts
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.manuscript_missing_keys import load_texts
from app.models import ManuscriptDraftReview as Row
from app.schemas.manuscript_draft_review import DraftReviewOut, DraftReviewState  # noqa: F401 (the MCP tools' types)

LIVE = timedelta(minutes=20)  # one long local-model call has no heartbeat inside it
JOB = "review_manuscript_draft"
logger = logging.getLogger(__name__)


def _live(row: Row) -> bool:
    return row.status in ("queued", "running") and datetime.now(UTC) - row.updated_at < LIVE


def review_out(row: Row) -> dict:
    dead = row.status in ("queued", "running") and not _live(row)
    return {
        "id": row.id,
        "mode": row.mode,
        "status": "interrupted" if dead else row.status,
        "stage": row.stage,
        "calls_done": row.calls_done,
        "calls_max": row.calls_max,
        "reason": row.reason,
        "issues": row.issues or [],
        "refuted": row.refuted or [],
        "counts": row.counts or {},
        "model": row.model,
        "ai": True,
        "created_at": row.created_at,
    }


async def _paper(session: AsyncSession, mid: uuid.UUID) -> tuple[str, dict[str, str]]:
    manuscript = await manuscripts.get(session, mid)
    files = {p: t for p, t in await load_texts(session, mid) if p.endswith(".tex")}
    if manuscript.main_file not in files:
        raise InvalidInput("not_tex", detail="The reviewer reads the main .tex file.")
    return assemble(files, manuscript.main_file)


async def estimate(session: AsyncSession, mid: uuid.UUID) -> dict:
    paper, _ = await _paper(session, mid)
    chars = len(paper)
    return {
        "paper_chars": chars,
        "too_long": chars > MAX_TOTAL_CHARS,
        "parts": len(split_parts(paper)),
        "modes": draft_review.estimates(paper),
    }


async def start(
    session: AsyncSession, mid: uuid.UUID, *, mode: str = "light", confirm_remote: bool, confirm_full: bool = False
) -> dict:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:mid))"), {"mid": str(mid)})
    await manuscripts.get(session, mid)
    await llm_connections.refuse_unconfirmed_remote(session, confirm_remote)
    paper, used = await _paper(session, mid)
    if len(paper) < MIN_PAPER_CHARS:
        raise InvalidInput("paper_too_short", detail="There is not enough text to review yet.")
    if len(paper) > MAX_TOTAL_CHARS:
        raise InvalidInput(
            "paper_too_long", detail="The draft is too long to review, even in parts.", limit=MAX_TOTAL_CHARS
        )
    parts = len(split_parts(paper))
    if mode not in draft_review.modes_for(parts):
        raise InvalidInput(
            "full_one_part",
            detail="A draft this long gets the light review only. "
            "The full review needs a draft under 40,000 characters.",
        )
    if mode == "full" and not confirm_full:  # the long run is asked for twice, like confirm_large elsewhere
        raise Conflict(
            "full_needs_confirm",
            likely_calls=draft_review.likely_calls("full", parts),
            max_calls=draft_review.max_calls("full", parts),
        )
    old = await session.scalars(select(Row).where(Row.manuscript_id == mid).execution_options(populate_existing=True))
    if any(_live(r) for r in old):
        raise Conflict("review_running")
    await session.execute(delete(Row).where(Row.manuscript_id == mid))
    row = Row(
        manuscript_id=mid,
        mode=mode,
        status="queued",
        calls_max=draft_review.max_calls(mode, parts),
        source=paper,
        # an array of [path, raw text] in the order the files went into the paper: JSONB would lose the key order
        inputs={"files": [[path, raw] for path, raw in used.items()]},
        confirm_remote=confirm_remote,
        updated_at=func.clock_timestamp(),
    )
    session.add(row)
    await session.commit()  # the job reads this row on its own connection
    await session.refresh(row)
    try:
        await queue.enqueue(JOB, str(row.id))
    except Exception:
        logger.exception("could not queue the draft review %s", row.id)
        row.status, row.reason = "failed", "queue_unavailable"
        await session.commit()
    return review_out(row)


async def cancel(session: AsyncSession, mid: uuid.UUID, review_id: uuid.UUID) -> dict:
    await manuscripts.get(session, mid)
    row = await session.scalar(
        select(Row).where(Row.id == review_id, Row.manuscript_id == mid).execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFound("unknown_review")
    if row.status in ("queued", "running"):
        row.status, row.reason, row.updated_at = "failed", "cancelled", func.clock_timestamp()  # a late write misses
        await session.commit()
        await session.refresh(row)
    return review_out(row)


async def state(session: AsyncSession, mid: uuid.UUID) -> dict:
    await manuscripts.get(session, mid)
    row = await session.scalar(
        select(Row)
        .where(Row.manuscript_id == mid)
        .order_by(Row.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return {"review": review_out(row) if row else None}
