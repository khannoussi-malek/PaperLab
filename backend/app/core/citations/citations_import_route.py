"""Starting a citations import: a preview, then applying inline or as a job for a big file, with its progress."""

import asyncio
import contextlib
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.citations.citations_bundle_read import Bundle, read_bundle
from app.core.citations.citations_import import ImportEntry
from app.core.citations.citations_import_apply import INLINE_MAX, JOB, ImportOptions, ImportResult, _held, apply
from app.core.citations.citations_parse import parse
from app.core.platform import queue
from app.core.workspaces import workspaces


def read(name: str, source: bytes | IO[bytes]) -> tuple[list[ImportEntry], Bundle | None]:
    """The entries of an uploaded file, and its Bundle when it is a zip (the caller closes it)."""
    if name.lower().endswith(".zip"):
        bundle = read_bundle(source)
        return bundle.entries, bundle
    return parse(name, source if isinstance(source, bytes) else source.read()), None


@dataclass(frozen=True)
class ImportPreview:
    """What an import would do, before it starts. cannot_import_without_fetch: entries neither held nor with a PDF
    in the zip, which only a free-copy fetch can make papers (fetching on or not); would_fetch: those of them that
    will contact free-copy sources (fetching on and a DOI or arXiv id)."""

    total: int
    already_in_library: int
    with_bundled_pdf: int
    would_fetch: int
    cannot_import_without_fetch: int
    # With save_without_pdf on, the entries that end as PDF-less papers unless a fetch finds a copy: those with no PDF
    # in the zip (an upper bound, since the fetch result is only known when it runs). 0 when it is off.
    would_save_without_pdf: int = 0
    # Bundled entries a damaged zip PDF would send to a free-copy lookup (_new_paper's fallback): for the disclosure.
    fallback_fetch: int = 0


async def preview(
    session: AsyncSession,
    entries: list[ImportEntry],
    *,
    bundle: Bundle | None = None,
    fetch_free_pdfs: bool = True,
    save_without_pdf: bool = False,
) -> ImportPreview:
    """apply's dedupe and choice of route, with no network call and nothing created.
    ponytail: three lookups per entry (_held); fine for a dialog, slow only near the 5,000-entry limit."""
    held = bundled = fetch = rest = fallback = 0
    for index, entry in enumerate(entries):
        if await _held(session, entry) is not None:
            held += 1
        elif bundle is not None and bundle.pdf_path(index):
            bundled += 1
            fallback += bool(fetch_free_pdfs and (entry.doi or entry.arxiv_id))
        else:
            rest += 1
            fetch += bool(fetch_free_pdfs and (entry.doi or entry.arxiv_id))
    return ImportPreview(
        len(entries), held, bundled, fetch, rest, would_save_without_pdf=rest if save_without_pdf else 0,
        fallback_fetch=fallback,
    )  # fmt: skip


def uploads_dir() -> Path:
    """Where start() leaves a file for the job (the api and the worker share pdf_dir)."""
    return settings.pdf_dir / "imports"


def progress_key(job_id: str) -> str:
    return f"{job_id}:progress"


def progress_payload(result: ImportResult, total: int, finished: bool) -> dict:
    """While running, counts only (needs_pdf and failed as numbers), so each write stays small; finished, the whole
    result. `done` counts the entries reached; `at` (time.time()) is the heartbeat a poll checks for a dead worker."""
    done = result.imported + result.already_in_library + result.saved_without_pdf
    done += len(result.needs_pdf) + len(result.failed)
    counts = {"total": total, "done": done, "finished": finished, "at": time.time()}
    if finished:
        return asdict(result) | counts
    tallies = ("imported", "already_in_library", "pdfs_attached", "saved_without_pdf", "notes")
    return {name: getattr(result, name) for name in tallies} | {
        "needs_pdf": len(result.needs_pdf), "failed": len(result.failed),
    } | counts  # fmt: skip


async def start(
    session: AsyncSession,
    name: str,
    source: bytes | IO[bytes],
    *,
    workspace_id: uuid.UUID | None = None,
    fetch_free_pdfs: bool = True,
    save_without_pdf: bool = False,
) -> ImportResult | str:
    """Imports a file now (INLINE_MAX entries or fewer, and none that would fetch: dedupe, zipped PDFs or fetch off),
    or queues the import_citations job and returns its id. `source` is the bytes or a seekable file (a zip is then
    read from it, never whole). Raises CitationsImportError for an unreadable file, NotFound for an unknown
    workspace."""
    if workspace_id is not None:
        await workspaces.require_writable(session, workspace_id)
    entries, bundle = read(name, source)
    with bundle or contextlib.nullcontext():
        options = ImportOptions(workspace_id, fetch_free_pdfs, save_without_pdf)
        return await route(session, name, source, entries, bundle, options)


def _copy(source: bytes | IO[bytes], path: Path) -> None:
    if isinstance(source, bytes):
        path.write_bytes(source)
        return
    source.seek(0)
    with open(path, "wb") as out:
        shutil.copyfileobj(source, out)


async def route(
    session: AsyncSession,
    name: str,
    source: bytes | IO[bytes],
    entries: list[ImportEntry],
    bundle: Bundle | None,
    options: ImportOptions = ImportOptions(),
) -> ImportResult | str:
    """start() for entries already read from `source` (its bundle still open). The job reads a copy of the file in
    uploads_dir(), deleted when it ends; its progress is a Redis value at progress_key(job id)."""
    small = len(entries) <= INLINE_MAX
    # ponytail: a damaged zip PDF's fallback lookup (fallback_fetch) still runs inline; queueing on it would send
    # nearly every Zotero zip to the background. Queue on it if those lookups ever stall a request.
    fetch = options.fetch_free_pdfs
    if small and not (await preview(session, entries, bundle=bundle, fetch_free_pdfs=fetch)).would_fetch:
        return await apply(session, entries, options, bundle=bundle)
    job_id = f"{JOB}:{uuid.uuid4()}"
    folder = uploads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{job_id.split(':')[1]}.upload"
    await asyncio.to_thread(_copy, source, path)
    try:
        workspace = str(options.workspace_id) if options.workspace_id else None
        await queue.enqueue(
            JOB, str(path), name, workspace, options.fetch_free_pdfs, options.save_without_pdf, job_id=job_id
        )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return job_id
