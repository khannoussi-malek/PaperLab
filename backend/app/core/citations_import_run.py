"""Importing a Zotero export from the app or over MCP (M40 Task 9a): the caps, the preview with its disclosure,
the import (inline, or the import_citations job), and reading a job's progress. Both surfaces call these; the work
itself is citations_import_apply's."""

import asyncio
import contextlib
import json
import re
import uuid
from dataclasses import asdict
from pathlib import Path

from arq.jobs import DeserializationError, Job, JobStatus
from arq.worker import JobExecutionFailed
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import citations_import_apply as cia
from app.core import workspaces
from app.core.citations_bundle_read import MAX_ZIP_BYTES
from app.core.citations_import import MAX_BYTES, CitationsImportError, ImportEntry
from app.core.errors import InvalidInput
from app.schemas.citations_import import ImportCountsOut, ImportPreviewOut, ImportProgressOut, ImportResultOut

FILE_MAX_BYTES = MAX_BYTES  # one references file
ZIP_MAX_BYTES = MAX_ZIP_BYTES  # a Zotero "export with files" zip
MB = 1024 * 1024
TOO_BIG = "This {kind} is larger than {mb} MB, which is more than PaperLab imports at once, so nothing was imported."
DISCLOSURE = (
    "Fetching contacts free-copy sources (Unpaywall, arXiv, …) for {count}, the same way adding a paper by DOI does."
)
RESTARTED = "PaperLab restarted during the import. Import the same file again; papers already imported are skipped."
EXPIRED = (
    "PaperLab no longer knows this import: it finished over a day ago or never started. Import the same file again "
    "if you need to; papers already imported are skipped."
)
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


def _check_size(name: str, size: int) -> None:
    if size > cap(name):
        raise InvalidInput(too_big(name))


def _read(name: str, data: bytes) -> list[ImportEntry]:
    """The file's entries; raises InvalidInput with the parser's plain message."""
    try:
        entries, bundle = cia.read(name, data)
    except CitationsImportError as exc:
        raise InvalidInput(str(exc)) from None
    with bundle or contextlib.nullcontext():
        return entries


def disclosure(would_fetch: int) -> str | None:
    if not would_fetch:
        return None
    return DISCLOSURE.format(count="1 entry" if would_fetch == 1 else f"{would_fetch:,} entries")


async def preview(
    session: AsyncSession, name: str, data: bytes, *, workspace_id: uuid.UUID | None = None,
    fetch_free_pdfs: bool = True,
) -> ImportPreviewOut:  # fmt: skip
    """What importing the file would do. Reads only: nothing is written and no paper source is contacted."""
    _check_size(name, len(data))
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    try:
        entries, bundle = cia.read(name, data)
    except CitationsImportError as exc:
        raise InvalidInput(str(exc)) from None
    with bundle or contextlib.nullcontext():
        counts = await cia.preview(session, entries, bundle=bundle, fetch_free_pdfs=fetch_free_pdfs)
    return ImportPreviewOut(**asdict(counts), disclosure=disclosure(counts.would_fetch))


async def start(
    session: AsyncSession, name: str, data: bytes, *, workspace_id: uuid.UUID | None = None,
    new_workspace_name: str | None = None, fetch_free_pdfs: bool = True,
) -> ImportProgressOut:  # fmt: skip
    """Imports the file inline (state finished) or queues the job (state queued, with its id). A new workspace is made
    only once the file has parsed, so a bad file creates nothing. Raises InvalidInput (too big, unreadable, both a
    workspace and a new name), NotFound (unknown workspace), Conflict (the new name is taken)."""
    _check_size(name, len(data))
    if workspace_id is not None and new_workspace_name is not None:
        raise InvalidInput("Choose an existing workspace or a new one, not both.")
    if new_workspace_name is not None:
        _read(name, data)  # ponytail: parsed twice (here and in cia.start), only when a workspace is made
        workspace_id = (await workspaces.create(session, new_workspace_name)).id
    try:
        outcome = await cia.start(session, name, data, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs)
    except CitationsImportError as exc:
        raise InvalidInput(str(exc)) from None
    if isinstance(outcome, str):
        return ImportProgressOut(state="queued", job_id=outcome, workspace_id=workspace_id)
    return ImportProgressOut(state="finished", workspace_id=workspace_id, result=ImportResultOut(**asdict(outcome)))


def _source(path_or_text: str) -> tuple[str, bytes]:
    """(name, bytes) of a local file path, or of the raw text of a references file. A path's size is checked before
    it is read."""
    text = path_or_text.lstrip()
    if "\n" in text or text.startswith(("@", "[", "{", "%")):
        data = path_or_text.encode()
        _check_size(RAW_TEXT_NAME, len(data))
        return RAW_TEXT_NAME, data
    path = Path(path_or_text.strip())
    try:
        size = path.stat().st_size if path.is_file() else None
    except OSError:
        size = None
    if size is None:
        raise InvalidInput("file_not_found", path=str(path))
    _check_size(path.name, size)
    return path.name, path.read_bytes()


async def start_from(
    session: AsyncSession, path_or_text: str | None, workspace: str | None = None, fetch_free_pdfs: bool = True
) -> ImportProgressOut:
    """start() for the MCP tool: a path or raw text, and a workspace by name."""
    if not (path_or_text or "").strip():
        raise InvalidInput("path_or_text_or_job_id_required")
    workspace_id = await workspaces.by_name(session, workspace) if workspace is not None else None
    name, data = _source(path_or_text)
    return await start(session, name, data, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs)


def _finished(job_id: str, payload: dict) -> ImportProgressOut:
    return ImportProgressOut(state="finished", job_id=job_id, result=ImportResultOut(**payload))


async def status(redis, job_id: str) -> ImportProgressOut:
    """A job's progress from its progress key (cia.progress_key) and arq's own record of the job. Never raises for an
    unknown, old or broken job: it answers expired, restarted or failed in words."""
    if not JOB_ID.fullmatch(job_id):
        return ImportProgressOut(state="expired", job_id=job_id, message=EXPIRED)
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
        return ImportProgressOut(state="running", job_id=job_id, counts=counts)
    if state in (JobStatus.queued, JobStatus.deferred):
        return ImportProgressOut(state="queued", job_id=job_id, counts=counts)
    if progress is not None:  # arq lost the job before it finished (killed outright)
        return ImportProgressOut(state="restarted", job_id=job_id, message=RESTARTED)
    return ImportProgressOut(state="expired", job_id=job_id, message=EXPIRED)
