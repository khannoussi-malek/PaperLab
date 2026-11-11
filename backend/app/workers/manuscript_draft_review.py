"""ARQ job: one whole-draft review (S2P B7). Reads only the row captured at start. Every write is stamped with the
row's updated_at and lands only while the row is the `running` one this job took, so a cancel (which changes the
stamp) makes the next write miss and the job stop, and a cancelled row stays cancelled. Pattern as
workers/manuscript_section_review.py."""

import logging
import uuid

from sqlalchemy import func, select, update

from app.core import draft_review
from app.core.errors import DomainError, error_code
from app.db import SessionLocal
from app.models import ManuscriptDraftReview as Row
from app.providers.base import LLMError, LLMUnavailable
from app.workers.manuscript_section_review import _model  # the default connection's model, as there

logger = logging.getLogger(__name__)
# full mode is up to 54 calls; each is under LIVE (20 min), so a run that looks live really is
DRAFT_REVIEW_JOB_TIMEOUT = 100 * 60


async def _take(review_id: uuid.UUID):
    """(paper, files, mode, confirm_remote, stamp) of a queued row, now running; None when gone or not queued."""
    async with SessionLocal() as session:
        row = await session.scalar(
            select(Row).where(Row.id == review_id, Row.status == "queued").with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        stamp = await session.scalar(
            update(Row)
            .where(Row.id == row.id)
            .values(status="running", updated_at=func.clock_timestamp())
            .returning(Row.updated_at)
        )
        await session.commit()
        files = {path: raw for path, raw in row.inputs["files"]}  # the array back to an ordered dict
        return row.source, files, row.mode, row.confirm_remote, stamp


async def _beat(review_id: uuid.UUID, stamp, **values):
    """The row's new stamp after a write, or None: the row is no longer the running one this job took (cancelled)."""
    async with SessionLocal() as session:
        new = await session.scalar(
            update(Row)
            .where(Row.id == review_id, Row.status == "running", Row.updated_at == stamp)
            .values(updated_at=func.clock_timestamp(), **values)
            .returning(Row.updated_at)
        )
        await session.commit()
        return new


async def review_manuscript_draft(ctx: dict, review_id: str) -> None:
    rid = uuid.UUID(review_id)
    taken = await _take(rid)
    if taken is None:
        return
    paper, files, mode, confirmed, stamp = taken
    holder = [stamp]  # the latest stamp; a write moves it

    async def progress(stage: str, done: int) -> bool:
        new = await _beat(rid, holder[0], stage=stage, calls_done=done)
        if new is None:
            return False
        holder[0] = new
        return True

    try:
        llm = await _model(ctx.get("llm"), confirmed)
        result = await draft_review.review(paper, files, llm=llm, progress=progress, mode=mode)
    except draft_review.Cancelled:
        return
    except DomainError as exc:
        values = {"status": "failed", "reason": error_code(exc)}
    except LLMUnavailable:
        values = {"status": "failed", "reason": "model_unavailable"}
    except (LLMError, draft_review.ReviewFailed):
        values = {"status": "failed", "reason": "model_error"}
    except Exception:
        logger.exception("draft review failed for %s", review_id)
        values = {"status": "failed", "reason": "check_failed"}
    else:
        values = {
            "status": "done",
            "stage": None,
            "issues": result.issues,
            "refuted": result.refuted,
            "counts": result.counts,
            "model": result.model,
            "calls_done": result.calls,
        }
    await _beat(rid, holder[0], **values)
