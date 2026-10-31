"""ARQ jobs: draw a diagram and compile its preview (M27 slice E). Same stamp discipline as the section review: taking
the row and writing the result are short transactions of their own, and the write lands only while the row is still
the `running` one this job took, so a cancelled row or a newer edit wins over a late result. The model comes from
ctx["llm"] and the compiler from ctx["compile"] when a test sets them."""

import logging
import uuid

from sqlalchemy import func, select, update

from app.core import diagram, diagram_compile
from app.core.errors import DomainError, error_code
from app.core.manuscript_diagrams import guard_errors
from app.db import SessionLocal
from app.models import ManuscriptDiagram as Row
from app.providers.base import LLMError, LLMUnavailable
from app.workers import manuscripts as compile_worker
from app.workers.manuscript_section_review import _model  # the default connection's model, as there

logger = logging.getLogger(__name__)

DIAGRAM_JOB_TIMEOUT = 18 * 60  # under LIVE, so a run that still looks live really is


async def _take(did: uuid.UUID):
    """(description, code, libraries, stamp) of a queued row, now running; None when gone or no longer queued."""
    async with SessionLocal() as session:
        row = await session.scalar(
            select(Row).where(Row.id == did, Row.status == "queued").with_for_update(skip_locked=True)
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
        return row.description, row.code, list(row.libraries or []), stamp


async def _write(did: uuid.UUID, stamp, **values) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Row)
            .where(Row.id == did, Row.status == "running", Row.updated_at == stamp)
            .values(updated_at=func.clock_timestamp(), **values)
        )
        await session.commit()


async def _compile(libraries: list[str], picture: str, compile_fn) -> dict:
    """The preview half. Code the guard refuses is never compiled; its errors are already on the row."""
    if errors := guard_errors(libraries, picture):
        return {"compiled": False, "errors": errors}
    # ponytail: the lock is per worker process and a manuscript compile can hold it a while; time spent waiting
    # counts toward LIVE, so a long queue reads `interrupted` — move the wait before _take if that shows up.
    async with compile_worker.COMPILE_LOCK:
        res = await (compile_fn or diagram_compile.preview)(libraries, picture)
    return {
        "compiled": res.ok,
        "errors": res.errors,
        "preview_pdf": res.pdf if res.ok else None,
        "reason": None if res.ok else res.friendly,
    }


async def _draw(description: str, ctx: dict) -> dict:
    got = await diagram.generate(description, llm=await _model(ctx.get("llm")))
    values = {
        "code": got.picture,
        "libraries": got.libraries,
        "labels_not_in_description": got.labels_not_in_description,
        "model": got.model,
    }
    return {**values, **await _compile(got.libraries, got.picture, ctx.get("compile")), "status": "done"}


async def generate_manuscript_diagram(ctx: dict, diagram_id: str) -> None:
    did = uuid.UUID(diagram_id)
    taken = await _take(did)
    if taken is None:
        return
    description, _, _, stamp = taken
    try:
        values = await _draw(description, ctx)
    except DomainError as exc:
        values = {"status": "failed", "reason": error_code(exc)}
    except LLMUnavailable:
        values = {"status": "failed", "reason": "model_unavailable"}
    except (LLMError, diagram.DiagramFailed):
        values = {"status": "failed", "reason": "model_error"}
    except Exception:
        logger.exception("diagram generation failed for %s", diagram_id)
        values = {"status": "failed", "reason": "check_failed"}
    await _write(did, stamp, **values)


async def compile_manuscript_diagram(ctx: dict, diagram_id: str) -> None:
    did = uuid.UUID(diagram_id)
    taken = await _take(did)
    if taken is None:
        return
    _, code, libraries, stamp = taken
    try:
        values = {**await _compile(libraries, code or "", ctx.get("compile")), "status": "done"}
    except Exception:
        logger.exception("diagram compile failed for %s", diagram_id)
        values = {"status": "failed", "reason": "compile_failed"}
    await _write(did, stamp, **values)
