"""ARQ job: one section review (M27 slice E). It reads only the row captured at start, never the file, so the result
belongs to the hash it was started on. Taking the row and writing the result are short transactions of their own, and
the write lands only while the row is still the `running` one this job took (the stamp), so a cancelled row stays
cancelled. The model comes from ctx["llm"] when a test sets it, else the default connection's."""

import logging
import uuid

from sqlalchemy import func, select, update

from app.core import llm_connections, section_review
from app.core.errors import DomainError, error_code
from app.db import SessionLocal
from app.models import ManuscriptSectionReview as Row
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import build_llm

logger = logging.getLogger(__name__)

SECTION_REVIEW_JOB_TIMEOUT = 25 * 60
PREVIEW_WORDS = 8


async def _take(review_id: uuid.UUID):
    """(role, inputs, stamp) of a queued row, now running; None when it is gone or no longer queued."""
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
        return row.role, row.inputs, stamp


async def _write(review_id: uuid.UUID, stamp, **values) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Row)
            .where(Row.id == review_id, Row.status == "running", Row.updated_at == stamp)
            .values(updated_at=func.clock_timestamp(), **values)
        )
        await session.commit()


def _refs(finding: section_review.Finding, inputs: dict) -> list[dict]:
    out = []
    for ref in finding.refs:
        if ref.kind == "S":
            words = inputs["sentences"][ref.n - 1].split()
            out.append(
                {
                    "kind": "sentence",
                    "n": ref.n,
                    "hash": inputs["hashes"][ref.n - 1],
                    "preview": " ".join(words[:PREVIEW_WORDS]),
                }
            )
        else:
            out.append({"kind": "note", "n": ref.n, **inputs["note_meta"][ref.n - 1]})
    return out


async def _model(llm):
    if llm is not None:
        return llm
    async with SessionLocal() as session:
        connection, model = await llm_connections.resolve(session, None)
        return build_llm(connection, model.name)


async def _judge(role: str, inputs: dict, llm) -> dict:
    result = await section_review.review(role, inputs["sentences"], inputs["notes"], llm=await _model(llm))
    findings = [{"kind": f.kind, "point": f.point, "refs": _refs(f, inputs)} for f in result.findings]
    return {"status": "done", "findings": findings, "dropped": result.dropped, "model": result.model}


async def review_manuscript_section(ctx: dict, review_id: str) -> None:
    rid = uuid.UUID(review_id)
    taken = await _take(rid)
    if taken is None:
        return
    role, inputs, stamp = taken
    try:
        values = await _judge(role, inputs, ctx.get("llm"))
    except DomainError as exc:
        values = {"status": "failed", "reason": error_code(exc)}
    except LLMUnavailable:
        values = {"status": "failed", "reason": "model_unavailable"}
    except (LLMError, section_review.ReviewFailed):
        values = {"status": "failed", "reason": "model_error"}
    except Exception:
        logger.exception("section review failed for %s", review_id)
        values = {"status": "failed", "reason": "check_failed"}
    await _write(rid, stamp, **values)
