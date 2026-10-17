"""ARQ job: import_citations (M40 Task 7), a Zotero import of more than citations_import_apply.INLINE_MAX entries.
Progress (the result so far, the entry count and whether it finished) is a Redis value at progress_key(job id)."""

import contextlib
import json
import uuid
from pathlib import Path

from app.core import citations_import_apply as cia
from app.db import SessionLocal

# ponytail: one entry can take several paced downloads; raise it if big fetching imports time out
IMPORT_JOB_TIMEOUT = 3 * 3600


async def import_citations(ctx: dict, path: str, name: str, workspace_id: str | None, fetch_free_pdfs: bool) -> dict:
    """The file at `path` (written by cia.start) is deleted when the job ends, whatever happens. Returns the result."""
    key = cia.progress_key(ctx["job_id"])
    try:
        with open(path, "rb") as upload:
            entries, bundle = cia.read(name, upload)
            total = len(entries)

            async def report(result: cia.ImportResult, finished: bool = False) -> None:
                payload = json.dumps(cia.progress_payload(result, total, finished))
                await ctx["redis"].set(key, payload, ex=cia.PROGRESS_TTL)

            async with SessionLocal() as session:
                with bundle or contextlib.nullcontext():
                    result = await cia.apply(
                        session, entries, workspace_id=uuid.UUID(workspace_id) if workspace_id else None,
                        fetch_free_pdfs=fetch_free_pdfs, bundle=bundle, progress=report,
                    )  # fmt: skip
    finally:
        Path(path).unlink(missing_ok=True)
    await report(result, finished=True)
    return cia.progress_payload(result, total, True)
