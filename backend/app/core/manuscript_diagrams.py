"""Diagram runs (M27 slice E): a TikZ picture drawn from the researcher's own description, checked by the guard and
compiled to a preview in the background. Nothing here writes into a manuscript file: the code goes in only on the
researcher's click, with an AI comment (D118). `code` is the only text a response carries, and only in DiagramOut."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import diagram, diagram_tikz, llm_connections, manuscripts, queue
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import ManuscriptDiagram as Row

LIVE = timedelta(minutes=20)  # one long local-model call has no heartbeat inside it
KEEP = 5
MAX_AGE = timedelta(days=7)
GENERATE_JOB = "generate_manuscript_diagram"
COMPILE_JOB = "compile_manuscript_diagram"
logger = logging.getLogger(__name__)


def _live(row: Row) -> bool:
    return row.status in ("queued", "running") and datetime.now(UTC) - row.updated_at < LIVE


def diagram_out(row: Row) -> dict:
    dead = row.status in ("queued", "running") and not _live(row)
    return {
        "id": row.id,
        "description": row.description,
        "status": "interrupted" if dead else row.status,
        "code": row.code,
        "libraries": row.libraries or [],
        "compiled": row.compiled,
        "errors": row.errors or [],
        "labels_not_in_description": row.labels_not_in_description or [],
        "reason": row.reason,
        "model": row.model,
        "ai": True,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def guard_errors(libraries: list[str], picture: str) -> list[dict]:
    return [{"line": None, "message": m} for m in diagram_tikz.check(libraries, picture)]


async def _row(session: AsyncSession, mid: uuid.UUID, did: uuid.UUID) -> Row:
    await manuscripts.get(session, mid)
    row = await session.scalar(
        select(Row).where(Row.id == did, Row.manuscript_id == mid).execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFound("unknown_diagram")
    return row


async def _enqueue(session: AsyncSession, row: Row, job: str) -> dict:
    await session.commit()  # the job reads this row on its own connection
    await session.refresh(row)
    try:
        await queue.enqueue(job, str(row.id))
    except Exception:
        logger.exception("could not queue %s for diagram %s", job, row.id)
        row.status, row.reason = "failed", "queue_unavailable"
        await session.commit()
    return diagram_out(row)


async def create(session: AsyncSession, mid: uuid.UUID, *, description: str, confirm_remote: bool) -> dict:
    # Creates on one manuscript take turns to the commit: the later one sees the earlier row and refuses.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"diagram:{mid}"})
    await manuscripts.get(session, mid)
    description = description.strip()
    if not description or len(description) > diagram.MAX_DESCRIPTION:
        raise InvalidInput("description_invalid", limit=diagram.MAX_DESCRIPTION)
    await llm_connections.refuse_unconfirmed_remote(session, confirm_remote)
    rows = list(
        await session.scalars(
            select(Row)
            .where(Row.manuscript_id == mid)
            .order_by(Row.created_at.desc())
            .execution_options(populate_existing=True)
        )
    )
    if any(_live(r) for r in rows):
        raise Conflict("diagram_running")
    old = [r.id for r in rows[KEEP - 1 :]] + [r.id for r in rows if datetime.now(UTC) - r.created_at > MAX_AGE]
    if old:
        await session.execute(delete(Row).where(Row.id.in_(old)))
    row = Row(
        manuscript_id=mid,
        description=description,
        status="queued",
        prompt_version=diagram.PROMPT_VERSION,
        created_at=func.clock_timestamp(),  # not now(): rows made in one transaction still sort newest last
        updated_at=func.clock_timestamp(),
    )
    session.add(row)
    return await _enqueue(session, row, GENERATE_JOB)


async def set_code(session: AsyncSession, mid: uuid.UUID, did: uuid.UUID, code: str) -> dict:
    """The researcher's own edit: re-checked and recompiled. A compile still running for an older edit is superseded
    (its write misses the new stamp); only a generation in progress refuses."""
    row = await _row(session, mid, did)
    if _live(row) and row.code is None:
        raise Conflict("diagram_running")
    libraries, picture = diagram_tikz.split_code(code)
    row.code, row.libraries, row.errors = picture, libraries, guard_errors(libraries, picture)
    row.labels_not_in_description = diagram_tikz.labels_not_in_description(picture, row.description)
    row.compiled, row.preview_pdf, row.reason = None, None, None
    row.status, row.updated_at = "queued", func.clock_timestamp()
    return await _enqueue(session, row, COMPILE_JOB)


async def cancel(session: AsyncSession, mid: uuid.UUID, did: uuid.UUID) -> dict:
    row = await _row(session, mid, did)
    if row.status in ("queued", "running"):
        row.status, row.reason, row.updated_at = "failed", "cancelled", func.clock_timestamp()  # a late write misses
        await session.commit()
        await session.refresh(row)
    return diagram_out(row)


async def remove(session: AsyncSession, mid: uuid.UUID, did: uuid.UUID) -> None:
    await session.delete(await _row(session, mid, did))
    await session.commit()


async def state(session: AsyncSession, mid: uuid.UUID, did: uuid.UUID) -> dict:
    return diagram_out(await _row(session, mid, did))


async def pdf(session: AsyncSession, mid: uuid.UUID, did: uuid.UUID) -> bytes:
    row = await _row(session, mid, did)
    if not row.preview_pdf:
        raise NotFound("no_preview")
    return row.preview_pdf
