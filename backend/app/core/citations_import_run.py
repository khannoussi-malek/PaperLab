"""Importing a Zotero export from the app or over MCP (M40 Task 9a): the caps, the preview with its disclosure,
the import (inline, or the import_citations job), and reading a job's progress. Both surfaces call these; the work
itself is citations_import_apply's."""

import asyncio
import contextlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import IO

from arq.jobs import DeserializationError, Job, JobStatus
from arq.worker import JobExecutionFailed
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import citations_import_apply as cia
from app.core import queue, workspaces
from app.core.citations_bundle_read import MAX_ZIP_BYTES, Bundle
from app.core.citations_import import MAX_BYTES, CitationsImportError, ImportEntry
from app.core.errors import InvalidInput
from app.schemas.citations_import import ImportCountsOut, ImportPreviewOut, ImportProgressOut, ImportResultOut

FILE_MAX_BYTES = MAX_BYTES  # one references file
ZIP_MAX_BYTES = MAX_ZIP_BYTES  # a Zotero "export with files" zip
MB = 1024 * 1024
TOO_BIG = "This {kind} is larger than {mb} MB, which is more than PaperLab imports at once, so nothing was imported."
DISCLOSURE = (
    "Fetching contacts free-copy sources (Unpaywall, arXiv, …) {target}, the same way adding a paper by DOI does."
)
UNREADABLE = "for a PDF in the zip that can't be read"
RESTARTED = "PaperLab restarted during the import. Import the same file again; papers already imported are skipped."
EXPIRED = (
    "PaperLab no longer knows this import: it finished over a day ago or never started. Import the same file again "
    "if you need to; papers already imported are skipped."
)
UNAVAILABLE = "PaperLab can't check this import right now. Try again in a moment; the import carries on."
BOTH = "Give job_id to read an import's progress, or path_or_text to start one, not both."
# A running job writes its progress (with `at`) before its first entry and after each one. One entry's worst case is
# a few minutes: a search across the sources, then each free PDF link tried at up to discovery.PDF_TIMEOUT (10 s to
# connect, 30 s to read), arXiv searches spaced out. A heartbeat older than this means the worker died without arq
# noticing (killed outright: its in-progress key outlives it by the whole job timeout, about 3 h).
HEARTBEAT_STALE = 15 * 60
JOB_FAILED = "Something went wrong during this import. Import the same file again; papers already imported are skipped."
JOB_ID = re.compile(rf"{cia.JOB}:[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}")
# How a job cut short by a restart ends: cancelled on shutdown, then refused on its retry (max_tries=1), or retried
# after its upload was deleted.
LOST = (JobExecutionFailed, asyncio.CancelledError, FileNotFoundError)
RAW_TEXT_NAME = "references"  # the file's kind is then read from its text


def is_zip(name: str) -> bool:
    return name.lower().endswith(".zip")


def cap(name: str) -> int:
    return ZIP_MAX_BYTES if is_zip(name) else FILE_MAX_BYTES


def too_big(name: str) -> str:
    return TOO_BIG.format(kind="zip" if is_zip(name) else "file", mb=cap(name) // MB)


# The request body's own cap, before the file's name (and so its kind) is known.
UPLOAD_TOO_BIG = TOO_BIG.format(kind="upload", mb=ZIP_MAX_BYTES // MB)


def _size(source: bytes | IO[bytes]) -> int:
    if isinstance(source, bytes):
        return len(source)
    size = source.seek(0, os.SEEK_END)
    source.seek(0)
    return size


def _check_size(name: str, source: bytes | IO[bytes]) -> None:
    if _size(source) > cap(name):
        raise InvalidInput(too_big(name))


def _read(name: str, source: bytes | IO[bytes]) -> tuple[list[ImportEntry], Bundle | None]:
    """The file's entries and its Bundle when it is a zip (the caller closes it); InvalidInput with the parser's plain
    message."""
    try:
        return cia.read(name, source)
    except CitationsImportError as exc:
        raise InvalidInput(str(exc)) from None


def disclosure(would_fetch: int, fallback_fetch: int = 0) -> str | None:
    """What a fetch would contact, or None. `fallback_fetch`: bundled entries whose zip PDF, if it can't be read, is
    looked up as a free copy instead (citations_import_apply._new_paper)."""
    count = "for 1 entry" if would_fetch == 1 else f"for {would_fetch:,} entries"
    if would_fetch and fallback_fetch:
        return DISCLOSURE.format(target=f"{count}, and {UNREADABLE}")
    if fallback_fetch:
        return DISCLOSURE.format(target=f"only {UNREADABLE}")
    return DISCLOSURE.format(target=count) if would_fetch else None


async def preview(
    session: AsyncSession, name: str, source: bytes | IO[bytes], *, workspace_id: uuid.UUID | None = None,
    fetch_free_pdfs: bool = True, save_without_pdf: bool = False,
) -> ImportPreviewOut:  # fmt: skip
    """What importing the file would do. Reads only: nothing is written and no paper source is contacted."""
    _check_size(name, source)
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    entries, bundle = _read(name, source)
    with bundle or contextlib.nullcontext():
        counts = await cia.preview(
            session, entries, bundle=bundle, fetch_free_pdfs=fetch_free_pdfs, save_without_pdf=save_without_pdf
        )
    shown = asdict(counts)
    fallback = shown.pop("fallback_fetch")  # only worded in the disclosure
    return ImportPreviewOut(**shown, disclosure=disclosure(counts.would_fetch, fallback))


async def start(
    session: AsyncSession, name: str, source: bytes | IO[bytes], *, workspace_id: uuid.UUID | None = None,
    new_workspace_name: str | None = None, fetch_free_pdfs: bool = True, save_without_pdf: bool = False,
) -> ImportProgressOut:  # fmt: skip
    """Imports the file inline (state finished) or queues the job (state queued, with its id). `source` is the bytes
    or a seekable file (a zip is read from it, never whole). The file is parsed once; a new workspace is made only
    once it has parsed, so a bad file creates nothing, and removed again if the import then fails to start. Raises
    InvalidInput (too big, unreadable, both a workspace and a new name), NotFound (unknown workspace), Conflict (the
    new name is taken)."""
    _check_size(name, source)
    if workspace_id is not None and new_workspace_name is not None:
        raise InvalidInput("Choose an existing workspace or a new one, not both.")
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    entries, bundle = _read(name, source)
    with bundle or contextlib.nullcontext():
        made = None
        if new_workspace_name is not None:
            made = workspace_id = (await workspaces.create(session, new_workspace_name)).id
        try:
            outcome = await cia.route(
                session, name, source, entries, bundle, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs,
                save_without_pdf=save_without_pdf,
            )
        except BaseException:
            # In practice only the job's enqueue fails here (apply keeps each entry's failure to itself), so the
            # workspace is still empty.
            if made is not None:
                await session.rollback()
                await workspaces.delete(session, made)
            raise
    if isinstance(outcome, str):
        return ImportProgressOut(state="queued", job_id=outcome, workspace_id=workspace_id)
    return ImportProgressOut(state="finished", workspace_id=workspace_id, result=ImportResultOut(**asdict(outcome)))


def _is_text(path_or_text: str) -> bool:
    text = path_or_text.lstrip()
    return "\n" in text or text.startswith(("@", "[", "{", "%"))


async def start_from(
    session: AsyncSession,
    path_or_text: str | None,
    workspace: str | None = None,
    fetch_free_pdfs: bool = True,
    save_without_pdf: bool = False,
) -> ImportProgressOut:
    """start() for the MCP tool: a local file path (its size checked before it is read, a zip read from the file)
    or the raw text of a references file, and a workspace by name."""
    if not (path_or_text or "").strip():
        raise InvalidInput("path_or_text_or_job_id_required")
    workspace_id = await workspaces.by_name(session, workspace) if workspace is not None else None
    if _is_text(path_or_text):
        data = path_or_text.encode()
        return await start(
            session, RAW_TEXT_NAME, data, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs,
            save_without_pdf=save_without_pdf,
        )
    path = Path(path_or_text.strip())
    try:
        size = path.stat().st_size if path.is_file() else None
    except OSError:
        size = None
    if size is None:
        raise InvalidInput("file_not_found", path=str(path))
    if size > cap(path.name):
        raise InvalidInput(too_big(path.name))
    with open(path, "rb") as file:
        return await start(
            session, path.name, file, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs,
            save_without_pdf=save_without_pdf,
        )


async def poll(job_id: str, path_or_text: str | None = None) -> ImportProgressOut:
    """status() for the MCP tool, through the process's arq pool."""
    if path_or_text is not None:
        raise InvalidInput(BOTH)
    return await status(await queue.pool(), job_id)


def _finished(job_id: str, payload: dict) -> ImportProgressOut:
    return ImportProgressOut(state="finished", job_id=job_id, result=ImportResultOut(**payload))


async def status(redis, job_id: str) -> ImportProgressOut:
    """A job's progress from its progress key (cia.progress_key) and arq's own record of the job. Never raises for an
    unknown, old or broken job, or for Redis being out of reach: it answers expired, restarted, failed or unavailable
    in words."""
    if not JOB_ID.fullmatch(job_id):
        return ImportProgressOut(state="expired", job_id=job_id, message=EXPIRED)
    try:
        return await _status(redis, job_id)
    except (RedisError, OSError):
        return ImportProgressOut(state="unavailable", job_id=job_id, message=UNAVAILABLE)


async def _status(redis, job_id: str) -> ImportProgressOut:
    raw = await redis.get(cia.progress_key(job_id))
    progress = json.loads(raw) if raw else None
    if progress and progress.get("finished"):
        return _finished(job_id, progress)
    counts = ImportCountsOut(**progress) if progress else None
    job = Job(job_id, redis)
    state = await job.status()
    if state is JobStatus.complete:
        try:
            info = await job.result_info()
        except DeserializationError:
            info = None
        if info is not None and info.success:
            return _finished(job_id, info.result)
        if info is not None and isinstance(info.result, LOST):
            return ImportProgressOut(state="restarted", job_id=job_id, message=RESTARTED)
        return ImportProgressOut(state="failed", job_id=job_id, message=JOB_FAILED)
    if state is JobStatus.in_progress:
        if progress is not None and time.time() - progress.get("at", 0) > HEARTBEAT_STALE:
            return ImportProgressOut(state="restarted", job_id=job_id, message=RESTARTED)
        return ImportProgressOut(state="running", job_id=job_id, counts=counts)
    if state in (JobStatus.queued, JobStatus.deferred):
        return ImportProgressOut(state="queued", job_id=job_id, counts=counts)
    if progress is not None:  # arq lost the job before it finished (killed outright)
        return ImportProgressOut(state="restarted", job_id=job_id, message=RESTARTED)
    return ImportProgressOut(state="expired", job_id=job_id, message=EXPIRED)
