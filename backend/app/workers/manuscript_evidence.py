"""ARQ job: a verdict for each paper's passages on one sentence, one paper at a time in rank order (M27 v2 stage 3).

The model comes from ctx["llm"] when a test sets it, else the default connection's model (verify_claim resolves it).
Taking a row and writing its result are short transactions of their own. verify_claim runs in a session of its own
whose read transaction stays open across the model call (it commits after, with the llm_outputs row). A write lands
only while its row is still the `running` one this job took, so a newer ask that re-queued the row is never
overwritten."""

import logging
import uuid

from sqlalchemy import func, select, update

from app.core import claims, llm_connections
from app.core.errors import DomainError, error_code
from app.db import SessionLocal
from app.models import ManuscriptEvidence

logger = logging.getLogger(__name__)

EVIDENCE_JOB_TIMEOUT = 30 * 60


async def _take(mid: uuid.UUID, sentence_hash: str):
    """The next queued row, marked running: (id, paper_id, sentence, confirm_remote, updated_at), or None."""
    async with SessionLocal() as session:
        row = await session.scalar(
            select(ManuscriptEvidence)
            .where(
                ManuscriptEvidence.manuscript_id == mid,
                ManuscriptEvidence.sentence_hash == sentence_hash,
                ManuscriptEvidence.status == "queued",
            )
            .order_by(ManuscriptEvidence.rank)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        stamp = await session.scalar(
            update(ManuscriptEvidence).where(ManuscriptEvidence.id == row.id)
            .values(status="running", updated_at=func.clock_timestamp()).returning(ManuscriptEvidence.updated_at)
        )
        # The rows still waiting are alive too, so they never read as interrupted while the job runs. Skip locked:
        # a row another job is taking right now is not waiting, and waiting on it could deadlock the two takes.
        waiting = (
            select(ManuscriptEvidence.id)
            .where(
                ManuscriptEvidence.manuscript_id == mid,
                ManuscriptEvidence.sentence_hash == sentence_hash,
                ManuscriptEvidence.status == "queued",
            )
            .with_for_update(skip_locked=True)
        )
        await session.execute(
            update(ManuscriptEvidence).where(ManuscriptEvidence.id.in_(waiting)).values(updated_at=func.clock_timestamp())
        )
        await session.commit()
        return row.id, row.paper_id, row.sentence, row.confirm_remote, stamp


async def _write(row_id: uuid.UUID, stamp, **values) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(ManuscriptEvidence)
            .where(ManuscriptEvidence.id == row_id, ManuscriptEvidence.status == "running",
                   ManuscriptEvidence.updated_at == stamp)
            .values(updated_at=func.clock_timestamp(), **values)
        )
        await session.commit()


async def verify_manuscript_evidence(ctx: dict, mid: str, sentence_hash: str) -> None:
    manuscript_id = uuid.UUID(mid)
    while (taken := await _take(manuscript_id, sentence_hash)) is not None:
        row_id, paper_id, sentence, confirmed, stamp = taken
        try:
            async with SessionLocal() as session:
                if ctx.get("llm") is None:  # the ask's yes, against the default as it is now
                    await llm_connections.refuse_unconfirmed_remote(session, confirmed)
                check = await claims.verify_claim(session, sentence, paper_id=paper_id, llm=ctx.get("llm"))
                await session.commit()  # the llm_outputs row
        except DomainError as exc:
            await _write(row_id, stamp, status="failed", reason=error_code(exc))
        except Exception:
            logger.exception("evidence check failed for manuscript %s", mid)
            await _write(row_id, stamp, status="failed", reason="check_failed")
        else:
            await _write(row_id, stamp, status="done", verdict=check.verdict, reason=check.reason, quote=check.quote,
                         page=check.quote_page, output_id=check.output_id)
