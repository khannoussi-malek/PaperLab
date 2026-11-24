"""Importing a workspace package: match its papers to the library, then write the workspace, papers, PDFs, tags, notes and record."""

import asyncio
import itertools
import logging
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.citations import citations_import_apply
from app.core.notes import ai_notes, notes
from app.core.papers import papers, pipeline_upload
from app.core.platform import queue
from app.core.search import discovery, same_work, screening
from app.core.workspaces import tags, workspace_package_answers, workspace_package_screening, workspaces
from app.core.workspaces.package_read import _made_on, _open, _Package, _read, _vet
from app.core.workspaces.workspace_package import INVALID, PAPER_FIELDS, _dump, record_path
from app.domain.candidates import Candidate
from app.domain.chunking import STRATEGY_VERSION
from app.domain.errors import InvalidInput
from app.domain.source_types import DETAILS_SOURCES
from app.models import Chunk, Note, Paper, PaperStatus, Workspace, WorkspaceTag, note_anchors
from app.models.tag import paper_tags
from app.models.workspace import workspace_papers

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ImportReport:
    workspace_id: uuid.UUID
    name: str
    added: int  # new papers
    matched: int  # papers the library already held
    notes: int
    pdfs_skipped: int  # a PDF that was too large, not a PDF, or missing from the zip
    has_record: bool  # the screening record was kept for download
    answers: int  # chat answers written to the workspace
    hits: int  # search results rebuilt from the screening (0 for a package without live screening)


def _identifiers(rec: dict) -> list[str]:
    """What a paper can be matched by, as strings that compare equal: a DOI, an OpenAlex id, a PMID, a PMCID."""
    pairs = (
        ("doi", rec.get("doi") and rec["doi"].lower()),
        ("oa", rec.get("openalex_id")),
        ("pmid", rec.get("pmid")),
        ("pmcid", rec.get("pmcid") and rec["pmcid"].upper()),
    )
    return [f"{kind}:{value}" for kind, value in pairs if value]


def _candidate(rec: dict) -> Candidate:
    oa = rec.get("openalex_id")
    return Candidate(
        title=rec["title"], authors=list(rec.get("authors") or []), year=rec.get("year"), venue=rec.get("venue"),
        doi=rec.get("doi"), abstract=rec.get("abstract"), external_ids={"openalex": oa} if oa else {},
    )  # fmt: skip


def _dois_differ(ours: str | None, theirs: str | None) -> bool:
    return bool(ours and theirs and ours.lower() != theirs.lower())


async def _title_match(session: AsyncSession, rec: dict, candidate: Candidate) -> uuid.UUID | None:
    """A library paper with the record's title under same_work's author and year rules, whose DOI does not differ from
    the record's and whose year is the same when both have one. Scans the titles that start with the first word."""
    first = next(iter(discovery.normal_title(rec["title"]).split()), "")
    if not first:
        return None
    rows = await session.execute(
        select(Paper.id, Paper.title, Paper.authors, Paper.year, Paper.doi).where(
            func.lower(Paper.title).startswith(first, autoescape=True)
        )
    )
    ours = {"title": rec["title"], "authors": candidate.authors, "year": candidate.year}
    for row in rows:
        if not same_work.same_work(Candidate(row.title, row.authors, row.year), ours):
            continue
        if _dois_differ(rec.get("doi"), row.doi):
            continue
        if None not in (candidate.year, row.year) and candidate.year != row.year:
            continue
        return row.id
    return None


async def _held(session: AsyncSession, rec: dict) -> uuid.UUID | None:
    """The library paper this one is, found without writing anything: DOI or OpenAlex id (discovery.mark_in_library),
    then PMID or PMCID, then the same title (_title_match). A matched paper is never changed by an import."""
    candidate = _candidate(rec)
    [marked] = await discovery.mark_in_library(session, [candidate])
    if marked.paper_id is not None:
        return marked.paper_id
    if by_id := await citations_import_apply.held_by_pubmed_ids(session, rec.get("pmid"), rec.get("pmcid")):
        return by_id
    return await _title_match(session, rec, candidate)


async def _resolve(session: AsyncSession, recs: list[dict]) -> tuple[dict[str, uuid.UUID], dict[str, str]]:
    """(held: key -> the library paper it is, alias: key -> the earlier key of a paper this package adds, with the same
    identifier, so a package listing one paper twice adds it once)."""
    held: dict[str, uuid.UUID] = {}
    alias: dict[str, str] = {}
    planned: dict[str, str] = {}
    for rec in recs:
        if (found := await _held(session, rec)) is not None:
            held[rec["key"]] = found
        elif (earlier := next((planned[i] for i in _identifiers(rec) if i in planned), None)) is not None:
            alias[rec["key"]] = earlier
        else:
            planned.update(dict.fromkeys(_identifiers(rec), rec["key"]))
    return held, alias


def _workspace_row(pkg: _Package, name: str) -> Workspace:
    meta = pkg.manifest["workspace"]
    line = f"Imported from a PaperLab package made on {_made_on(pkg.manifest)}."
    description = "\n".join(filter(None, [(meta.get("description") or "").strip() or None, line]))
    row = Workspace(
        name=name, description=description, research_question=meta.get("research_question") or None,
        inclusion_criteria=meta.get("inclusion_criteria") or None,
        exclusion_criteria=meta.get("exclusion_criteria") or None, read_only=True,
    )  # fmt: skip
    row.screening_criteria = screening._criteria_summary(row)
    return row


async def _free_name(session: AsyncSession, name: str) -> str:
    """The name, or `<name> (2)`, `(3)`… when taken; a suffixed base is cut so the whole name stays within the limit."""
    for number in itertools.count(1):
        suffix = "" if number == 1 else f" ({number})"
        candidate = name if number == 1 else name[: workspaces.NAME_MAX_CHARS - len(suffix)].rstrip() + suffix
        if await session.scalar(select(Workspace.id).where(Workspace.name == candidate)) is None:
            return candidate
    raise AssertionError("unreachable")  # itertools.count never ends


def _write_atomic(path: Path, write: Callable[[Path], None]) -> None:
    """Writes to a temp name in the same folder, then moves it into place: a failed write leaves no partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _copy_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, path: Path) -> None:
    def write(tmp: Path) -> None:
        with zf.open(info) as source, tmp.open("wb") as target:
            shutil.copyfileobj(source, target)

    _write_atomic(path, write)


def _pdf_member(zf: zipfile.ZipFile, rec: dict) -> zipfile.ZipInfo | None:
    """The member a paper names, when it is a PDF PaperLab takes (within the upload cap and starting %PDF-)."""
    name = rec.get("pdf")
    if not name or name not in zf.NameToInfo:
        return None
    info = zf.getinfo(name)
    if info.file_size > pipeline_upload.MAX_UPLOAD_PDF_BYTES:
        return None
    with zf.open(info) as source:
        return info if source.read(len(papers.PDF_MAGIC)) == papers.PDF_MAGIC else None


async def _new_paper(session, pkg: _Package, rec: dict, written: list[Path], queued: list) -> tuple[Paper, bool]:
    """A paper this package adds, with its PDF when it has a good one (its ingest queued), else as details only (its
    abstract indexed, when it has one). Returns (the paper, whether its PDF was skipped)."""
    paper_id = uuid.uuid4()
    info = _pdf_member(pkg.zf, rec) if rec.get("pdf") else None
    skipped = bool(rec.get("pdf")) and info is None
    fields = {name: rec[name] for name in PAPER_FIELDS if rec.get(name) is not None and name != "details_source"}
    abstract = (rec.get("abstract") or "").strip() or None
    if info is not None:
        path = settings.pdf_dir / f"{paper_id}.pdf"
        await asyncio.to_thread(_copy_member, pkg.zf, info, path)
        written.append(path)
        fields |= {"file_path": str(path), "status": PaperStatus.UPLOADED}
        source = rec.get("details_source")
        fields |= {"details_source": source} if source in DETAILS_SOURCES else {}
    else:
        fields |= {
            "details_source": rec.get("details_source") if rec.get("details_source") in DETAILS_SOURCES else "manual"
        }
        fields |= {"status": PaperStatus.EMBEDDING if abstract else PaperStatus.READY}
    paper = Paper(id=paper_id, **fields)
    session.add(paper)
    await session.flush()
    if info is not None:
        queued.append(("ingest_paper", str(paper_id)))
    elif abstract:
        session.add_all(
            Chunk(
                paper_id=paper_id,
                ordinal=d.ordinal,
                page=d.page,
                bbox=d.bbox,
                section_title=d.section_title,
                text=d.text,
                embed_model=settings.embed_model,
                strategy_ver=STRATEGY_VERSION,
            )  # fmt: skip
            for d in papers.abstract_drafts(paper.title, abstract)
        )
        queued.append(("index_abstract", str(paper_id)))
    return paper, skipped


async def _papers_into(session, pkg, workspace_id, held, alias, written, queued) -> tuple[dict, int, int, int]:
    """Links every package paper to the workspace. Returns (key -> paper id, added, matched, pdfs skipped); matched
    counts the distinct library papers."""
    ids: dict[str, uuid.UUID] = {}
    library: set[uuid.UUID] = set()
    added = skipped = 0
    for rec in pkg.papers:
        key, member = rec["key"], rec.get("member", True)  # a non-member is a paper the screening names only
        if key in alias:
            paper_id = ids[alias[key]]
        elif key in held:
            paper_id = held[key]
            if member:
                library.add(paper_id)
        else:
            paper, was_skipped = await _new_paper(session, pkg, rec, written, queued)
            paper_id = paper.id
            if member:
                added, skipped = added + 1, skipped + int(was_skipped)
        ids[key] = paper_id
        if member:
            await session.execute(
                insert(workspace_papers).values(workspace_id=workspace_id, paper_id=paper_id).on_conflict_do_nothing()
            )
    return ids, added, len(library), skipped


async def _tags_into(session, workspace_id, rows: list[dict], ids: dict) -> None:
    """One tag per name (case-insensitive, as in the workspace), on the papers the package lists."""
    by_name: dict[str, WorkspaceTag] = {}
    for row in rows:
        name = tags.normalize(row["name"])
        tag = by_name.get(name.lower())
        if tag is None:
            tag = WorkspaceTag(workspace_id=workspace_id, name=name)
            session.add(tag)
            await session.flush()
            by_name[name.lower()] = tag
        placed = [{"workspace_id": workspace_id, "paper_id": ids[k], "tag_id": tag.id} for k in row.get("papers") or []]
        if placed:
            await session.execute(insert(paper_tags).values(placed).on_conflict_do_nothing())


async def _chunk_for(session, paper_id: uuid.UUID, page: int, quoted: str) -> uuid.UUID | None:
    """The chunk on this page that holds the quote, when the paper has its text here; else None (the column is kept
    for a later locate, never guessed)."""
    needle = notes.fold(quoted or "")
    if not needle:
        return None
    for chunk in await papers.list_chunks(session, paper_id, page):
        if ai_notes.quote_hits(chunk.text, needle):
            return chunk.id
    return None


def _moment(value: str | None, default: datetime) -> datetime:
    """An exported timestamp as the notes table keeps it: naive, in UTC (its columns have no time zone)."""
    if not value:
        return default
    moment = datetime.fromisoformat(value)
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


async def _notes_into(session, rows: list[dict], ids: dict) -> int:
    for row in rows:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        note = Note(
            body=row["body"], provenance=row["provenance"], kind=row.get("kind"),
            color=notes.normalize_color(row.get("color") or notes.DEFAULT_COLOR),
            created_at=_moment(row.get("created_at"), now), updated_at=_moment(row.get("updated_at"), now),
        )  # fmt: skip
        session.add(note)
        await session.flush()
        await notes._link(session, note.id, [ids[k] for k in row.get("papers") or []])
        for hl in row.get("highlights") or []:
            paper_id = ids[hl["paper"]]
            await session.execute(
                insert(note_anchors)
                .values(
                    note_id=note.id,
                    paper_id=paper_id,
                    page=hl["page"],
                    bbox=[list(map(float, r)) for r in hl["rects"]],
                    quoted_text=hl.get("quoted_text") or "",
                    chunk_id=await _chunk_for(session, paper_id, hl["page"], hl.get("quoted_text") or ""),
                )
                .on_conflict_do_nothing()
            )
    return len(rows)


def _write_bytes(path: Path, data: bytes) -> None:
    _write_atomic(path, lambda tmp: tmp.write_bytes(data))


async def _record_into(pkg: _Package, workspace_id: uuid.UUID, written: list[Path]) -> None:
    path = record_path(workspace_id)
    await asyncio.to_thread(_write_bytes, path, _dump({"screening": pkg.screening, "prisma": pkg.prisma}))
    written.append(path)


async def _write_package(session, pkg: _Package, name: str, held, alias) -> ImportReport:
    written: list[Path] = []
    queued: list[tuple[str, str]] = []
    try:
        workspace = _workspace_row(pkg, name)
        session.add(workspace)
        await session.flush()
        ids, added, matched, skipped = await _papers_into(session, pkg, workspace.id, held, alias, written, queued)
        await _tags_into(session, workspace.id, pkg.tags, ids)
        note_count = await _notes_into(session, pkg.notes, ids)
        answer_count = await workspace_package_answers.write_rows(session, workspace.id, pkg.answers, ids)
        hit_count = 0
        if workspace_package_screening.is_v2(pkg.screening):
            hit_count = await workspace_package_screening.rebuild(session, pkg.screening, workspace, ids)
            await session.flush()
            full_text = workspace_package_screening.full_text_in_package(pkg.screening, pkg.papers)
            if not await workspace_package_screening.counts_match(session, workspace.id, pkg.prisma, full_text):
                raise InvalidInput(INVALID, detail="screening counts don't match")
        else:
            await _record_into(pkg, workspace.id, written)
        await session.commit()
    except BaseException:
        await session.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
    for job, arg in queued:  # only once the rows are committed, so a worker always finds its paper
        try:
            await queue.enqueue(job, arg)
        except Exception:
            logger.exception("could not queue %s for paper %s; it stays uploaded until it is queued again", job, arg)
    has_record = not workspace_package_screening.is_v2(pkg.screening)
    return ImportReport(
        workspace.id, name, added, matched, note_count, skipped, has_record, answer_count, hit_count
    )


async def import_package(session: AsyncSession, data: bytes | IO[bytes]) -> ImportReport:
    """A `.paperlab` file as a new workspace (named after the original, numbered when taken). Raises InvalidInput with
    package_unknown_format, package_unsafe, package_too_large or package_invalid; nothing is written then, and a
    failure partway writes nothing either (the rows in one transaction, the PDFs removed)."""
    zf = _open(data)
    with zf:
        _vet(zf)
        pkg = _read(zf)
        held, alias = await _resolve(session, pkg.papers)
        name = await _free_name(session, _name_of(pkg))
        return await _write_package(session, pkg, name, held, alias)


def _name_of(pkg: _Package) -> str:
    name = pkg.manifest["workspace"].get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= workspaces.NAME_MAX_CHARS:
        raise InvalidInput(INVALID)
    return name.strip()
