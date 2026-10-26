"""ARQ job: compile a manuscript with Tectonic on the main worker (M27a). Loops while another compile was requested."""

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.core import manuscript_history, manuscripts
from app.core.latex_compile import COMPILE_TIMEOUT, compile_dir
from app.core.manuscript_bib import build_bib
from app.db import SessionLocal
from app.models import Manuscript, ManuscriptFile

logger = logging.getLogger(__name__)

COMPILE_JOB_TIMEOUT = 4 * (COMPILE_TIMEOUT + 30)
# One Tectonic run per worker process: they share a cache and each takes memory.
_COMPILE_LOCK = asyncio.Lock()


def _write_files(workdir: Path, rows) -> None:
    root = workdir.resolve()
    for path, text, data in rows:
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            logger.warning("manuscript file %r escapes the workdir; skipped", path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if text is None else text.encode())


def _write_pdf(manuscript_id: uuid.UUID, pdf: bytes) -> None:
    target = manuscripts.pdf_path(manuscript_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pdf)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


async def _compile(workdir: Path, main_file: str):
    async with _COMPILE_LOCK:
        return await compile_dir(workdir, main_file)


async def _pass(session, manuscript: Manuscript) -> None:
    """One compile; commits its own result."""
    mid = manuscript.id
    rows = (await session.execute(select(ManuscriptFile.path, ManuscriptFile.text, ManuscriptFile.data)
                                  .where(ManuscriptFile.manuscript_id == mid))).all()
    sources = {p: t for p, t, _ in rows if t is not None}
    bib = await build_bib(session, manuscript, sources)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        _write_files(workdir, rows)
        (workdir / "paperlab.bib").write_text(bib, encoding="utf-8")
        result = await _compile(workdir, manuscript.main_file)
    if result.ok and result.pdf is not None:
        _write_pdf(mid, result.pdf)
        await manuscript_history.take(session, mid, "compile")
    await session.execute(update(Manuscript).where(Manuscript.id == mid).values(
        compile_status="ok" if result.ok else "failed", compile_log=result.log,
        compile_errors=result.errors, compiled_at=datetime.now(UTC)))
    await session.commit()


async def _mark_failed(session, mid: uuid.UUID, error: Exception) -> None:
    await session.rollback()
    await session.execute(update(Manuscript).where(Manuscript.id == mid).values(
        compile_status="failed", compile_log=f"internal error: {type(error).__name__}", compiled_at=datetime.now(UTC)))
    await session.commit()


async def compile_manuscript(ctx: dict, manuscript_id: str) -> None:
    mid = uuid.UUID(manuscript_id)
    async with SessionLocal() as session:
        again = True
        while again:
            try:
                manuscript = await session.get(Manuscript, mid, populate_existing=True)
                if manuscript is None:
                    return  # deleted meanwhile
                manuscript.compile_requested = False  # a request that arrives during this pass earns one more
                manuscript.compile_status = "running"
                await session.commit()
                await _pass(session, manuscript)
                again = bool((await session.get(Manuscript, mid, populate_existing=True)).compile_requested)
            except Exception as error:
                logger.exception("compiling manuscript %s failed", mid)
                await _mark_failed(session, mid, error)
                return
