"""Turn a parsed Zotero import into papers (M40 Task 7, D267–D269, ruling A). Every paper has a PDF, so an entry
becomes a paper only with one: its PDF from the zip, else (fetch_free_pdfs) a free copy found the way Add paper finds
one. Without either it is listed in `needs_pdf` and nothing is created.

- Dedupe comes first, with today's rules: discovery.mark_in_library (DOI, a preprint's published DOI, OpenAlex id),
  discovery.held_version (the arXiv copy or the published version), then the exact title under _same_work. A match
  is attached as it is: its fields are never written (held_version itself records a published version on a held
  arXiv copy, as everywhere else).
- Zotero notes become unanchored notes by You. Into a workspace, tags become its tags on the paper; the collection
  (and, library-only, the tags) go in one short "From Zotero — …" note. A note body the paper already has is skipped,
  so importing a file twice adds nothing.
- Each entry stands alone: one that fails is listed in `failed`, a paper it created is removed, and the rest go on.
- Imports over INLINE_MAX entries run as the import_citations job (app/workers/citations_import.py)."""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import IO

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import discovery, notes, papers, queue, tags, workspaces
from app.core.candidates import Candidate, normal_title
from app.core.citations_bundle_read import Bundle, read_bundle
from app.core.citations_import import CitationsImportError, ImportEntry, parse
from app.core.errors import Conflict, DomainError
from app.core.source_types import peer_reviewed_of
from app.models import Note, Paper, Provenance, note_papers

logger = logging.getLogger(__name__)

INLINE_MAX = 50
JOB = "import_citations"
PROGRESS_TTL = 24 * 3600
FAILED = "Something went wrong importing this reference. Try importing it again."
FROM_ZOTERO = "From Zotero — "
EXTRA_FIELDS = ("volume", "issue", "pages", "issn", "pmid", "pmcid")


@dataclass(frozen=True)
class ImportResult:
    imported: int = 0  # new papers
    already_in_library: int = 0
    pdfs_attached: int = 0  # new papers whose PDF came from the zip; the rest of `imported` were fetched
    notes: int = 0
    needs_pdf: list[dict] = field(default_factory=list)  # {title, doi, tried, free_copies}
    failed: list[dict] = field(default_factory=list)  # {title, reason}

    def __add__(self, other: "ImportResult") -> "ImportResult":
        return ImportResult(
            *(getattr(self, f) + getattr(other, f) for f in ("imported", "already_in_library", "pdfs_attached")),
            self.notes + other.notes, [*self.needs_pdf, *other.needs_pdf], [*self.failed, *other.failed],
        )  # fmt: skip


Progress = Callable[[ImportResult], Awaitable[None]]


def _candidate(entry: ImportEntry) -> Candidate:
    return Candidate(
        title=entry.title, authors=entry.authors, year=entry.year, venue=entry.venue, doi=entry.doi,
        abstract=entry.abstract, external_ids={"arxiv": entry.arxiv_id} if entry.arxiv_id else {},
    )  # fmt: skip


async def _same_title(session: AsyncSession, entry: ImportEntry) -> uuid.UUID | None:
    """A library paper with the entry's exact title under _same_work's author and year rules (M63b).
    ponytail: scans the titles that start with the entry's first word, as _reuse_published_copy does (no title
    index)."""
    first = next(iter(normal_title(entry.title).split()), "")
    if not first:
        return None
    columns = (Paper.id, Paper.title, Paper.authors, Paper.year)
    rows = await session.execute(select(*columns).where(func.lower(Paper.title).startswith(first, autoescape=True)))
    ours = {"title": entry.title, "authors": entry.authors, "year": entry.year}
    return next(
        (row.id for row in rows if discovery._same_work(Candidate(row.title, row.authors, row.year), ours)), None
    )


async def _held(session: AsyncSession, entry: ImportEntry) -> uuid.UUID | None:
    candidate = _candidate(entry)
    [marked] = await discovery.mark_in_library(session, [candidate])
    if marked.paper_id is not None:
        return marked.paper_id
    if (other := await discovery.held_version(session, candidate)) is not None:
        return other[0]
    return await _same_title(session, entry)


def _prefill(entry: ImportEntry) -> dict:
    """discovery.prefill's fields and locks (title, and the DOI), plus what else the entry knows."""
    fields = discovery.prefill(_candidate(entry))
    fields |= {name: value for name in EXTRA_FIELDS if (value := getattr(entry, name))}
    if entry.editors:
        fields["editors"] = entry.editors
    if entry.source_type != "other":
        fields |= {"source_type": entry.source_type, "peer_reviewed": peer_reviewed_of(entry.source_type)}
    return fields


async def _add_note(session: AsyncSession, paper_id: uuid.UUID, body: str) -> None:
    """An unanchored note by You on the paper, as notes_markdown.import_files makes one."""
    note = Note(body=body, provenance=Provenance.HUMAN)
    session.add(note)
    await session.flush()
    await notes._link(session, note.id, [paper_id])


def _zotero_note(entry: ImportEntry, note_tags: list[str]) -> str | None:
    parts = [f"tags: {', '.join(note_tags)}" if note_tags else None,
             f"collection: {entry.collection}" if entry.collection else None]  # fmt: skip
    return FROM_ZOTERO + "; ".join(p for p in parts if p) if any(parts) else None


async def _file(session: AsyncSession, paper_id: uuid.UUID, entry: ImportEntry, workspace_id: uuid.UUID | None) -> int:
    """The entry's workspace, tags and notes on the paper. Returns how many notes were added."""
    note_tags = list(entry.tags)
    if workspace_id is not None:
        await workspaces.add_paper(session, workspace_id, paper_id)
        too_long = [t for t in entry.tags if len(t.strip()) > tags.NAME_MAX_CHARS]  # kept in the note instead
        for name in (t for t in entry.tags if t.strip() and t not in too_long):
            await tags.tag_papers(session, workspace_id, name, paper_ids=[paper_id])
        note_tags = too_long
    linked = select(note_papers.c.note_id).where(note_papers.c.paper_id == paper_id)
    have = set(await session.scalars(select(Note.body).where(Note.id.in_(linked))))
    added = 0
    for body in (*entry.notes, _zotero_note(entry, note_tags)):
        if body and body not in have:
            await _add_note(session, paper_id, body)
            have.add(body)
            added += 1
    await session.commit()
    return added


async def _fetch(session: AsyncSession, providers, entry: ImportEntry) -> tuple[Paper | uuid.UUID | None, dict]:
    """Add paper's free-copy flow (pipeline._add_found): by DOI, else arXiv id. Returns (the new Paper, or a held
    paper's id, or None with what was tried)."""
    _, value = discovery.classify_query(entry.doi or entry.arxiv_id)
    found = await discovery.search(session, providers, value)
    match = next(
        (c for c in found.results if (c.doi or "").lower() == value or c.external_ids.get("arxiv") == value), None
    )
    if match is None:
        return None, {"tried": [], "free_copies": []}
    if match.paper_id is not None:
        return match.paper_id, {}
    try:
        return await discovery.add(session, providers, match, settings.pdf_dir), {}
    except Conflict as exc:
        if str(exc) == discovery.ALREADY_IN_LIBRARY and "paper_id" in exc.details:
            return exc.details["paper_id"], {}
        if str(exc) != discovery.NO_FREE_PDF:
            raise
        return None, {"tried": exc.details.get("tried", []), "free_copies": exc.details.get("free_copies", [])}


async def _discard(session: AsyncSession, paper_id: uuid.UUID) -> None:
    """A paper this import just created, with the notes linked to it (all this import's)."""
    await session.rollback()
    linked = select(note_papers.c.note_id).where(note_papers.c.paper_id == paper_id)
    await session.execute(delete(Note).where(Note.id.in_(linked)))
    await papers.delete_paper(session, paper_id)


async def _new_paper(session, entry, providers, pdf: bytes | None) -> tuple[Paper | uuid.UUID | None, dict]:
    if pdf is not None:
        name = discovery._filename(entry.title)
        return await papers.create_paper(session, name, pdf, settings.pdf_dir, prefill=_prefill(entry)), {}
    if providers is None or not (entry.doi or entry.arxiv_id):
        return None, {"tried": [], "free_copies": []}
    return await _fetch(session, providers, entry)


async def _one(session, entry, workspace_id, providers, bundle: Bundle | None, index: int) -> ImportResult:
    held = await _held(session, entry)
    if held is not None:
        return ImportResult(already_in_library=1, notes=await _file(session, held, entry, workspace_id))
    member = bundle.pdf_path(index) if bundle is not None else None
    pdf = bundle.read_pdf(member) if member else None
    made, missing = await _new_paper(session, entry, providers, pdf)
    if made is None:
        return ImportResult(needs_pdf=[{"title": entry.title, "doi": entry.doi, **missing}])
    if not isinstance(made, Paper):  # the free-copy search found it held after all
        return ImportResult(already_in_library=1, notes=await _file(session, made, entry, workspace_id))
    try:
        added = await _file(session, made.id, entry, workspace_id)
        await queue.enqueue("ingest_paper", str(made.id))
    except BaseException:
        await _discard(session, made.id)
        raise
    return ImportResult(imported=1, pdfs_attached=int(pdf is not None), notes=added)


async def _isolated(session, entry, workspace_id, providers, bundle, index) -> ImportResult:
    try:
        return await _one(session, entry, workspace_id, providers, bundle, index)
    except (CitationsImportError, DomainError) as exc:
        await session.rollback()
        return ImportResult(failed=[{"title": entry.title, "reason": str(exc)}])
    except Exception:  # one entry's surprise must not stop the rest
        logger.exception("importing %r failed", entry.title)
        await session.rollback()
        return ImportResult(failed=[{"title": entry.title, "reason": FAILED}])


async def apply(
    session: AsyncSession,
    entries: list[ImportEntry],
    *,
    workspace_id: uuid.UUID | None = None,
    fetch_free_pdfs: bool = True,
    bundle: Bundle | None = None,
    progress: Progress | None = None,
) -> ImportResult:
    """The entries as papers, one at a time (the zip's PDFs are read one by one). Raises NotFound for an unknown
    workspace before anything is created; anything else an entry raises is listed in `failed`."""
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    result = ImportResult()
    fetches = fetch_free_pdfs and any(
        (e.doi or e.arxiv_id) and not (bundle and bundle.pdf_path(i)) for i, e in enumerate(entries)
    )
    opened = discovery.open_providers(session) if fetches else contextlib.nullcontext()
    async with opened as providers:  # one set of clients, so arXiv title searches stay paced across the import
        for index, entry in enumerate(entries):
            result += await _isolated(session, entry, workspace_id, providers, bundle, index)
            if progress is not None:
                await progress(result)
    return result


# ---- inline or a job ----


def read(name: str, source: bytes | IO[bytes]) -> tuple[list[ImportEntry], Bundle | None]:
    """The entries of an uploaded file, and its Bundle when it is a zip (the caller closes it)."""
    if name.lower().endswith(".zip"):
        bundle = read_bundle(source)
        return bundle.entries, bundle
    return parse(name, source if isinstance(source, bytes) else source.read()), None


def progress_key(job_id: str) -> str:
    return f"{job_id}:progress"


def progress_payload(result: ImportResult, total: int, finished: bool) -> dict:
    return asdict(result) | {"total": total, "finished": finished}


async def start(
    session: AsyncSession,
    name: str,
    data: bytes,
    *,
    workspace_id: uuid.UUID | None = None,
    fetch_free_pdfs: bool = True,
) -> ImportResult | str:
    """Imports a file now (INLINE_MAX entries or fewer), or queues the import_citations job and returns its id. The
    job reads a copy of the file under settings.pdf_dir/imports, deleted when it ends; its progress is a Redis value
    at progress_key(job id). Raises CitationsImportError for an unreadable file, NotFound for an unknown workspace."""
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    entries, bundle = read(name, data)
    with bundle or contextlib.nullcontext():
        if len(entries) <= INLINE_MAX:
            return await apply(
                session, entries, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs, bundle=bundle
            )
    job_id = f"{JOB}:{uuid.uuid4()}"
    folder = settings.pdf_dir / "imports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{job_id.split(':')[1]}.upload"
    await asyncio.to_thread(path.write_bytes, data)
    try:
        await queue.enqueue(JOB, str(path), name, str(workspace_id) if workspace_id else None, fetch_free_pdfs,
                            job_id=job_id)  # fmt: skip
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return job_id
