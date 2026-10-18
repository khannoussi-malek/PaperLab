"""ARQ job: import_citations (M40 Task 7), a Zotero import that fetches free PDFs or has more than
citations_import_apply.INLINE_MAX entries. Progress is a Redis value at progress_key(job id): counts while it runs,
the whole result once finished."""

import contextlib
import json
import logging
import time
import uuid
from pathlib import Path

from redis.exceptions import RedisError

from app.core import citations_import_apply as cia
from app.db import SessionLocal

log = logging.getLogger(__name__)

# ponytail: 5,000 fetching entries at 3–10 s each outrun it; the job then stops and lists what it didn't reach
IMPORT_JOB_TIMEOUT = 3 * 3600
# The loop stops itself this much before the registered timeout, so it still writes a finished result.
SAFETY_MARGIN = 120
STALE_UPLOAD = 24 * 3600  # a job killed outright never deletes its upload: the next job sweeps it


def _sweep_stale_uploads() -> None:
    cutoff = time.time() - STALE_UPLOAD
    for path in cia.uploads_dir().glob("*.upload"):
        with contextlib.suppress(FileNotFoundError):
            if path.stat().st_mtime < cutoff:
                path.unlink()


async def import_citations(ctx: dict, path: str, name: str, workspace_id: str | None, fetch_free_pdfs: bool) -> dict:
    """The file at `path` (written by cia.start) is deleted when the job ends, whatever happens. Returns the result."""
    deadline = time.monotonic() + IMPORT_JOB_TIMEOUT - SAFETY_MARGIN
    _sweep_stale_uploads()
    key = cia.progress_key(ctx["job_id"])
    total = 0

    async def report(result: cia.ImportResult, finished: bool = False) -> None:
        # A missed write only ages the heartbeat; it must not end a multi-hour import.
        try:
            await ctx["redis"].set(key, json.dumps(cia.progress_payload(result, total, finished)), ex=cia.PROGRESS_TTL)
        except (RedisError, OSError):
            log.warning("import progress write failed for %s; skipping", key, exc_info=True)

    try:
        with open(path, "rb") as upload:
            entries, bundle = cia.read(name, upload)
            total = len(entries)

            async with SessionLocal() as session:
                with bundle or contextlib.nullcontext():
                    await report(cia.ImportResult())  # the first heartbeat; apply reports after each entry
                    result = await cia.apply(
                        session, entries, workspace_id=uuid.UUID(workspace_id) if workspace_id else None,
                        fetch_free_pdfs=fetch_free_pdfs, bundle=bundle, progress=report, deadline=deadline,
                    )  # fmt: skip
    finally:
        Path(path).unlink(missing_ok=True)
    await report(result, finished=True)
    return cia.progress_payload(result, total, True)
