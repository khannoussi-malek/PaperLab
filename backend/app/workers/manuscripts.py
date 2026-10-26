"""ARQ job: compile a manuscript with Tectonic on the main worker (M27a). Loops while another compile was requested."""

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.config import settings
from app.core import manuscript_history, manuscripts
from app.core.latex_compile import COMPILE_TIMEOUT, compile_dir
from app.core.manuscript_bib import build_bib
from app.db import SessionLocal
from app.models import Manuscript, ManuscriptFile

logger = logging.getLogger(__name__)

COMPILE_JOB_TIMEOUT = 4 * (COMPILE_TIMEOUT + 30)
# One Tectonic run per worker process: they share a cache and each takes memory.
_COMPILE_LOCK = asyncio.Lock()
# The user's PDFs stay root-only while Tectonic runs as another user (isolation layer 3). WorkerSettings has no
# on_startup (see settings.py), so the first compile in the process does it.
_PDF_DIR_LOCKED = False


def _lock_pdf_dir() -> None:
    global _PDF_DIR_LOCKED
    if not _PDF_DIR_LOCKED:
        settings.pdf_dir.mkdir(parents=True, exist_ok=True)
        settings.pdf_dir.chmod(0o700)
        _PDF_DIR_LOCKED = True


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


async def _prepare(mid: uuid.UUID):
    """Short transaction 1: claim the pass, read the files, pin cited keys. None when the manuscript is gone."""
    async with SessionLocal() as session:
        manuscript = await session.get(Manuscript, mid, populate_existing=True)
        if manuscript is None:
            return None
        manuscript.compile_requested = False  # a request that arrives during this pass earns one more
        manuscript.compile_status = "running"
        manuscript.compile_started_at = datetime.now(UTC)  # keeps the stale window honest on every pass
        rows = (await session.execute(select(ManuscriptFile.path, ManuscriptFile.text, ManuscriptFile.data)
                                      .where(ManuscriptFile.manuscript_id == mid))).all()
        bib = await build_bib(session, manuscript, {p: t for p, t, _ in rows if t is not None})
        main_file = manuscript.main_file
        await session.commit()
        return main_file, rows, bib


async def _run_tectonic(main_file: str, rows, bib: str):
    """No database transaction is open here: a compile takes up to a minute."""
    _lock_pdf_dir()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        _write_files(workdir, rows)
        (workdir / "paperlab.bib").write_text(bib, encoding="utf-8")
        return await compile_dir(workdir, main_file)


async def _store(mid: uuid.UUID, result) -> bool:
    """Short transaction 2: the result. False (nothing written) when the manuscript was deleted meanwhile."""
    async with SessionLocal() as session:
        # NO KEY UPDATE keeps a delete out until we commit, yet lets the snapshot's foreign key through.
        locked = select(Manuscript.id).where(Manuscript.id == mid).with_for_update(key_share=True)
        if await session.scalar(locked) is None:
            return False
        if result.ok and result.pdf is not None:
            _write_pdf(mid, result.pdf)
            await manuscript_history.take(session, mid, "compile")
        await session.execute(update(Manuscript).where(Manuscript.id == mid).values(
            compile_status="ok" if result.ok else "failed", compile_log=result.log,
            compile_errors=result.errors,
            compile_friendly=None if result.ok else result.friendly, compiled_at=datetime.now(UTC)))
        await session.commit()
        return True


async def _mark_failed(mid: uuid.UUID, error: Exception) -> None:
    async with SessionLocal() as session:
        await session.execute(update(Manuscript).where(Manuscript.id == mid).values(
            compile_status="failed", compile_log=f"internal error: {type(error).__name__}", compile_friendly=None,
            compiled_at=datetime.now(UTC)))
        await session.commit()


async def compile_manuscript(ctx: dict, manuscript_id: str) -> None:
    # ponytail: an ARQ timeout cancels us (CancelledError is not an Exception), leaving the row `running`; the stale
    # window in request_compile (COMPILE_TIMEOUT + 60 s) lets the next request queue a fresh job.
    mid = uuid.UUID(manuscript_id)
    again = True
    while again:
        try:
            async with _COMPILE_LOCK:  # taken first, so time spent waiting never counts toward the stale window
                prepared = await _prepare(mid)
                if prepared is None:
                    return  # deleted meanwhile
                result = await _run_tectonic(*prepared)
                if not await _store(mid, result):
                    return
            async with SessionLocal() as session:
                again = bool(await session.scalar(select(Manuscript.compile_requested).where(Manuscript.id == mid)))
        except Exception as error:
            logger.exception("compiling manuscript %s failed", mid)
            await _mark_failed(mid, error)
            return
