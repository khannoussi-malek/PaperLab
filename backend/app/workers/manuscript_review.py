"""ARQ job: the citation reviewer's checks for one run, one row at a time in document order (M27 slice D).

Like the evidence job: taking a row and writing its result are short transactions of their own, and a write lands only
while its row is still the `running` one this job took (the stamp), so a newer start that replaced the rows is never
overwritten. The model comes from ctx["llm"] when a test sets it, else the default connection's."""

import logging
import uuid

from sqlalchemy import func, select, update

from app.core import claim_detect, claims, llm_connections
from app.core.errors import DomainError, error_code
from app.db import SessionLocal
from app.models import ManuscriptClaimCheck as Check
from app.models import ManuscriptReviewRun as Run
from app.providers.llm import build_llm

logger = logging.getLogger(__name__)

REVIEW_JOB_TIMEOUT = 60 * 60
MAX_REASON = 300


async def _take(run_id: uuid.UUID):
    """The next queued row, marked running: (id, kind, paper_id, plain, stamp), or None."""
    async with SessionLocal() as session:
        row = await session.scalar(
            select(Check)
            .where(Check.run_id == run_id, Check.status == "queued")
            .order_by(Check.ord)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        stamp = await session.scalar(
            update(Check)
            .where(Check.id == row.id)
            .values(status="running", updated_at=func.clock_timestamp())
            .returning(Check.updated_at)
        )
        # The rows still waiting are alive too, so they never read as interrupted while the job runs.
        waiting = (
            select(Check.id).where(Check.run_id == run_id, Check.status == "queued").with_for_update(skip_locked=True)
        )
        await session.execute(update(Check).where(Check.id.in_(waiting)).values(updated_at=func.clock_timestamp()))
        await session.execute(
            update(Run).where(Run.id == run_id).values(status="running", updated_at=func.clock_timestamp())
        )
        await session.commit()
        return row.id, row.kind, row.paper_id, row.plain, stamp


async def _write(run_id: uuid.UUID, row_id: uuid.UUID, stamp, **values) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            update(Check)
            .where(Check.id == row_id, Check.status == "running", Check.updated_at == stamp)
            .values(updated_at=func.clock_timestamp(), **values)
        )
        if result.rowcount:  # a replaced row isn't this run's progress
            await session.execute(
                update(Run).where(Run.id == run_id).values(done=Run.done + 1, updated_at=func.clock_timestamp())
            )
        await session.commit()


async def _judge(kind: str, paper_id, plain: str, llm) -> dict:
    """The values to store for one row; raises what the model call raises."""
    async with SessionLocal() as session:
        if kind == "cited":
            check = await claims.verify_claim(session, plain, paper_id=paper_id, llm=llm)
            await session.commit()  # the llm_outputs row
            return {
                "status": "done",
                "verdict": check.verdict,
                "reason": (check.reason or "")[:MAX_REASON],
                "quote": check.quote,
                "page": check.quote_page,
                "chunk_id": check.quote_chunk_id,
                "output_id": check.output_id,
                "model": check.model,
            }
        if llm is None:
            connection, model = await llm_connections.resolve(session, None)
            llm = build_llm(connection, model.name)
    found = await claim_detect.classify(plain, llm=llm)
    if found.reason == claim_detect.MODEL_ERROR:
        return {"status": "done", "verdict": "cannot_verify", "reason": claim_detect.MODEL_ERROR, "model": found.model}
    return {
        "status": "done",
        "verdict": "claim" if found.is_claim else "not_claim",
        "reason": found.reason,
        "model": found.model,
    }


async def _finish(run_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        run = await session.scalar(
            select(Run).where(Run.id == run_id).with_for_update().execution_options(populate_existing=True)
        )
        if run is None:
            return
        if run.cancel_requested:
            await session.execute(
                update(Check)
                .where(Check.run_id == run_id, Check.status == "queued")
                .values(status="failed", reason="cancelled", updated_at=func.clock_timestamp())
            )
        run.status = "cancelled" if run.cancel_requested else "done"
        run.updated_at = func.clock_timestamp()
        await session.commit()


async def _cancelled(run_id: uuid.UUID) -> bool | None:
    """True when a stop was asked for, None when the run is gone (a newer start replaced it)."""
    async with SessionLocal() as session:
        return await session.scalar(
            select(Run.cancel_requested).where(Run.id == run_id).execution_options(populate_existing=True)
        )


async def check_manuscript_citations(ctx: dict, run_id: str) -> None:
    rid = uuid.UUID(run_id)
    while (stop := await _cancelled(rid)) is False and (taken := await _take(rid)) is not None:
        row_id, kind, paper_id, plain, stamp = taken
        try:
            values = await _judge(kind, paper_id, plain, ctx.get("llm"))
        except DomainError as exc:
            values = {"status": "failed", "reason": error_code(exc)}
        except Exception:
            logger.exception("review check failed for run %s", run_id)
            values = {"status": "failed", "reason": "check_failed"}
        await _write(rid, row_id, stamp, **values)
    if stop is not None:
        await _finish(rid)
