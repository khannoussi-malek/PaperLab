"""A workspace as one `.paperlab` file (M35a, D199): a zip holding the workspace, its papers' details (and their PDFs
when asked), tags, notes with their highlights and provenance, and a read-only screening record (`screening.json`, the
runs and every hit's decisions, with an AI suggestion marked `ai`, and `prisma.json`, the counts).

Inside the file papers are keyed `p1…pN` and runs `r1…rN`, never by database id. Nothing secret or local goes in: no
API key, connection, paper-source setting, contact email, file path or database id."""

import asyncio
import io
import itertools
import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import IO, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import (
    citations_bundle_read,
    citations_import_apply,
    discovery,
    notes,
    papers,
    pipeline,
    prisma_export,
    queue,
    screening,
    search_run_results,
    tags,
    workspace_package_answers,
    workspace_package_screening,
    workspaces,
)  # fmt: skip
from app.core.candidates import Candidate
from app.core.chunking import STRATEGY_VERSION
from app.core.citations_bundle import SPOOL_BYTES
from app.core.citations_import import CitationsImportError
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.source_types import DETAILS_SOURCES
from app.core.workspace_package_shapes import (
    AnswersDoc,
    Manifest,
    NotesDoc,
    PapersDoc,
    PrismaTotals,
    ScreeningV2,
    TagsDoc,
)
from app.models import Chunk, Note, Paper, PaperStatus, Workspace, WorkspaceTag, note_anchors
from app.models.tag import paper_tags
from app.models.workspace import workspace_papers
from app.models.workspace_search import WorkspaceSearchRun

logger = logging.getLogger(__name__)

FORMAT = "paperlab-workspace"
FORMAT_VERSION = 1
PAPER_FIELDS = (
    "doi", "openalex_id", "pmid", "pmcid", "title", "abstract", "authors", "year", "venue", "type", "source_type",
    "peer_reviewed", "published_doi", "published_venue", "volume", "issue", "pages", "issn", "editors",
    "manual_fields", "details_source", "field_sources",
)  # fmt: skip
WORKSPACE_FIELDS = ("name", "description", "research_question", "inclusion_criteria", "exclusion_criteria")


def _paperlab_version() -> str:
    try:
        return version("paperlab")
    except PackageNotFoundError:
        return "unknown"


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _paper_row(key: str, paper: Paper, pdf: str | None, member: bool = True) -> dict:
    row = {
        "key": key,
        "member": member,
        **{name: getattr(paper, name) for name in PAPER_FIELDS},
        "has_pdf": paper.has_pdf,
    }
    return row | ({"pdf": pdf} if pdf else {})


def _notes_json(views, keys: dict[uuid.UUID, str]) -> list[dict]:
    """Each note with the workspace's own papers only: a link to a paper outside the workspace stays in the library."""
    out = []
    for number, view in enumerate(views, start=1):
        out.append({
            "key": f"n{number}", "body": view.body, "provenance": view.provenance, "color": view.color,
            "kind": view.kind, "created_at": _iso(view.created_at), "updated_at": _iso(view.updated_at),
            "papers": [keys[pid] for pid in view.paper_ids if pid in keys],
            "highlights": [
                {"paper": keys[a.paper_id], "page": a.page, "rects": [list(r) for r in a.bbox],
                 "quoted_text": a.quoted_text}
                for a in view.anchors if a.paper_id in keys
            ],
        })  # fmt: skip
    return out


async def _tags_json(session: AsyncSession, workspace_id: uuid.UUID, keys: dict[uuid.UUID, str]) -> list[dict]:
    by_name: dict[str, list[str]] = {}
    for paper_id, names in (await tags.paper_tag_map(session, workspace_id)).items():
        for name in names:
            if paper_id in keys:
                by_name.setdefault(name, []).append(keys[paper_id])
    return [{"name": name, "papers": by_name[name]} for name in sorted(by_name, key=str.lower)]


async def _runs(session: AsyncSession, workspace_id: uuid.UUID) -> tuple[list[WorkspaceSearchRun], dict, dict]:
    """The workspace's runs in start order, their keys (r1…) and their display names."""
    query = select(WorkspaceSearchRun).where(WorkspaceSearchRun.workspace_id == workspace_id)
    runs = list((await session.scalars(query.order_by(WorkspaceSearchRun.started_at, WorkspaceSearchRun.id))).all())
    keys = {run.id: f"r{number}" for number, run in enumerate(runs, start=1)}
    return runs, keys, await search_run_results.run_labels(session, runs)


async def _prisma_json(session: AsyncSession, workspace_id: uuid.UUID, keys: dict) -> dict:
    """prisma_export's combined counts, with each run's database id swapped for its key."""
    prisma = asdict(await prisma_export.prisma_export(session, workspace_id, None))
    prisma["runs"] = [
        {k: v for k, v in run.items() if k != "id"} | {"key": keys[uuid.UUID(run["id"])]} for run in prisma["runs"]
    ]
    return prisma


def _write(parts: dict[str, bytes], pdfs: list[tuple[str, Path]]) -> IO[bytes]:
    out = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    try:
        with zipfile.ZipFile(out, "w") as zf:
            for name, data in parts.items():
                zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            for name, path in pdfs:  # PDFs are already compressed: store them
                zf.write(path, name, compress_type=zipfile.ZIP_STORED)
        out.seek(0)
        return out
    except BaseException:
        out.close()
        raise


def _dump(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode()


async def _parts(
    session: AsyncSession, workspace_id: uuid.UUID, pdfs: bool, answers: bool
) -> tuple[dict[str, bytes], list]:
    """The package's members (name -> bytes) and the PDFs to put in it. Raises NotFound for an unknown workspace. With
    `answers`, answers.json holds the chat answers that carry a snapshot."""
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound(f"workspace {workspace_id} not found")
    members = await workspaces.papers(session, workspace_id)
    keys = {paper.id: f"p{number}" for number, paper in enumerate(members, start=1)}
    pdf_of = {
        p.id: (f"pdfs/{keys[p.id]}.pdf", Path(p.file_path))
        for p in members if pdfs and p.file_path and Path(p.file_path).is_file()
    }  # fmt: skip
    pdf_files = list(pdf_of.values())
    runs, run_keys, labels = await _runs(session, workspace_id)
    live = await workspace_package_screening.load(session, workspace_id, runs)
    outside = await workspace_package_screening.outside_papers(session, live, set(keys))
    screen_keys = keys | {paper.id: f"p{len(members) + number}" for number, paper in enumerate(outside, start=1)}
    papers_json = {"papers": [
        _paper_row(keys[p.id], p, pdf_of[p.id][0] if p.id in pdf_of else None) for p in members
    ] + [_paper_row(screen_keys[p.id], p, None, member=False) for p in outside]}  # fmt: skip
    workspace_row = await session.get(Workspace, workspace_id)
    screening = workspace_package_screening.document(live, workspace_row, run_keys, labels, screen_keys)
    prisma = await _prisma_json(session, workspace_id, run_keys)
    note_views = await workspaces.notes(session, workspace_id)
    answer_rows, answers_skipped = (
        await workspace_package_answers.export_rows(session, workspace_id, keys) if answers else ([], 0)
    )
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "paperlab_version": _paperlab_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": {name: getattr(workspace, name) for name in WORKSPACE_FIELDS},
        "counts": {
            "papers": len(members), "notes": len(note_views), "pdfs": len(pdf_files),
            "answers": len(answer_rows), "answers_skipped": answers_skipped,
        },
    }  # fmt: skip
    parts = {
        "manifest.json": _dump(manifest),
        "papers.json": _dump(papers_json),
        "notes.json": _dump({"notes": _notes_json(note_views, keys)}),
        "tags.json": _dump({"tags": await _tags_json(session, workspace_id, keys)}),
        "screening.json": _dump(screening),
        "prisma.json": _dump(prisma),
    }
    if answers:
        parts["answers.json"] = _dump({"answers": answer_rows})
    return parts, pdf_files


def _fits_import(parts: dict[str, bytes], pdf_files: list) -> None:
    """Refuses a package the import would refuse: any JSON member over its cap, or the whole, PDFs included, over the
    zip cap (the import counts every member)."""
    if any(len(data) > MAX_JSON_BYTES for data in parts.values()):
        raise Conflict("package_too_large")
    total = sum(len(data) for data in parts.values()) + sum(path.stat().st_size for _, path in pdf_files)
    if total > citations_bundle_read.MAX_ZIP_BYTES:
        raise Conflict(TOO_LARGE_WITH_PDFS if pdf_files else "package_too_large")


async def export_package(
    session: AsyncSession, workspace_id: uuid.UUID, *, pdfs: bool, answers: bool = True
) -> IO[bytes]:
    """The workspace as a zip file positioned at 0. Raises NotFound for an unknown workspace. With `pdfs`, each paper
    whose PDF is on disk is included; a paper whose PDF is missing is listed without one. Raises Conflict
    (package_too_large_with_pdfs) when, with its PDFs, the package would be more than the import takes. `answers` adds
    the chat answers (answers.json)."""
    parts, pdf_files = await _parts(session, workspace_id, pdfs, answers)
    _fits_import(parts, pdf_files)
    return await asyncio.to_thread(_write, parts, pdf_files)


async def check_export(session: AsyncSession, workspace_id: uuid.UUID, *, pdfs: bool, answers: bool = True) -> None:
    """Raises what export_package would for this workspace, without writing the zip (the dialog asks first)."""
    parts, pdf_files = await _parts(session, workspace_id, pdfs, answers)
    _fits_import(parts, pdf_files)


# ---- import (M35a Task 2) ----
#
# Two phases. Phase 1 finds each package paper's match in the library (discovery.held_version may commit on its own, so
# nothing is written yet). Phase 2 writes the workspace, papers, tags and notes in one transaction; PDFs and the record
# file are written before its commit and removed if anything fails.

UNKNOWN_FORMAT = "package_unknown_format"
UNSAFE = "package_unsafe"
TOO_LARGE = "package_too_large"
TOO_LARGE_WITH_PDFS = "package_too_large_with_pdfs"  # an export that the import would refuse
INVALID = "package_invalid"
MAX_JSON_BYTES = 20 * 1024 * 1024
JSON_MEMBERS = ("manifest.json", "papers.json", "notes.json", "tags.json", "screening.json", "prisma.json")


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


@dataclass(frozen=True)
class _Package:
    zf: zipfile.ZipFile
    manifest: dict
    papers: list[dict]
    notes: list[dict]
    tags: list[dict]
    screening: dict
    prisma: dict
    answers: list[dict]


def _invalid(detail: str = INVALID) -> InvalidInput:
    return InvalidInput(detail)


def _open(data: bytes | IO[bytes]) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise InvalidInput(UNKNOWN_FORMAT) from None


def _vet(zf: zipfile.ZipFile) -> None:
    """citations_bundle_read's zip checks, from the central directory alone. Too many members or too many bytes is
    package_too_large; any other refusal is package_unsafe."""
    infos = zf.infolist()
    too_many = len(infos) > citations_bundle_read.MAX_MEMBERS
    if too_many or sum(i.file_size for i in infos) > citations_bundle_read.MAX_ZIP_BYTES:
        raise InvalidInput(TOO_LARGE)
    try:
        citations_bundle_read._vet(infos)
    except CitationsImportError:
        raise InvalidInput(UNSAFE) from None


def _no_nul(value):
    """The value with NUL characters removed from every string (Postgres text and JSONB refuse them). A new value."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_no_nul(item) for item in value]
    if isinstance(value, dict):
        return {_no_nul(key): _no_nul(item) for key, item in value.items()}
    return value


def _json(zf: zipfile.ZipFile, name: str):
    if name not in zf.NameToInfo:
        raise InvalidInput(INVALID)
    info = zf.getinfo(name)
    if info.file_size > MAX_JSON_BYTES:
        raise InvalidInput(TOO_LARGE)
    try:
        return _no_nul(json.loads(zf.read(info)))
    except (ValueError, OSError, RuntimeError, EOFError, NotImplementedError, zipfile.BadZipFile, zlib.error):
        raise InvalidInput(INVALID) from None


def _supported(version) -> bool:
    return isinstance(version, int) and not isinstance(version, bool) and 1 <= version <= FORMAT_VERSION


def _made_on(manifest: dict) -> str:
    try:
        return datetime.fromisoformat(manifest["created_at"]).date().isoformat()
    except (KeyError, TypeError, ValueError):
        raise InvalidInput(INVALID) from None


def _shaped(model: type[BaseModel], doc):
    """The document, when it takes the shape the model describes; package_invalid otherwise. Never a server error."""
    try:
        model.model_validate(doc)
    except ValidationError:
        raise InvalidInput(INVALID) from None
    return doc


def _check_papers(doc) -> list[dict]:
    rows = doc["papers"]
    keys = [row["key"] for row in rows]
    if len(set(keys)) != len(keys) or not all(row["title"].strip() for row in rows):
        raise InvalidInput(INVALID)
    return rows


def _check_notes(doc, keys: set[str]) -> list[dict]:
    rows = doc["notes"]
    for row in rows:
        listed = set(row.get("papers") or [])
        highlights = row.get("highlights") or []
        if not listed <= keys or any(h["paper"] not in listed for h in highlights):
            raise InvalidInput(INVALID)
    return rows


def _check_tags(doc, keys: set[str]) -> list[dict]:
    rows = doc["tags"]
    if not all(set(r.get("papers") or []) <= keys for r in rows):
        raise InvalidInput(INVALID)
    return rows


def _answer_rows(zf: zipfile.ZipFile) -> list[dict]:
    """answers.json's rows when the package has the member; a package from before M35b2 has none and no answers."""
    if "answers.json" not in zf.NameToInfo:
        return []
    return _shaped(AnswersDoc, _json(zf, "answers.json"))["answers"]


def _check_screening_v2(screening: dict, prisma: dict, paper_keys: set[str]) -> None:
    """A version 2 screening takes its shape, names only keys the package holds, and prisma.json carries the totals
    the count check reads."""
    _shaped(ScreeningV2, screening)
    _shaped(PrismaTotals, prisma)
    try:
        workspace_package_screening.check_references(screening, paper_keys)
    except ValueError:
        raise InvalidInput(INVALID) from None


def _read(zf: zipfile.ZipFile) -> _Package:
    """Every member, checked: the manifest first (a file without one, or of another format, is refused before anything
    else is read). Each JSON member must take the shape its model describes."""
    if "manifest.json" not in zf.NameToInfo:
        raise InvalidInput(UNKNOWN_FORMAT)
    manifest = _json(zf, "manifest.json")
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != FORMAT
        or not _supported(manifest.get("format_version"))
    ):
        raise InvalidInput(UNKNOWN_FORMAT)
    _shaped(Manifest, manifest)
    papers_rows = _check_papers(_shaped(PapersDoc, _json(zf, "papers.json")))
    keys = {row["key"] for row in papers_rows}
    notes_rows = _check_notes(_shaped(NotesDoc, _json(zf, "notes.json")), keys)
    tag_rows = _check_tags(_shaped(TagsDoc, _json(zf, "tags.json")), keys)
    screening, prisma = _json(zf, "screening.json"), _json(zf, "prisma.json")
    if not isinstance(screening, dict) or not isinstance(prisma, dict):
        raise InvalidInput(INVALID)
    if workspace_package_screening.is_v2(screening):
        _check_screening_v2(screening, prisma, {row["key"] for row in papers_rows})
    _made_on(manifest)
    return _Package(zf, manifest, papers_rows, notes_rows, tag_rows, screening, prisma, _answer_rows(zf))


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
        if not discovery.same_work(Candidate(row.title, row.authors, row.year), ours):
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
    if info.file_size > pipeline.MAX_UPLOAD_PDF_BYTES:
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
        if notes.quote_hits(chunk.text, needle):
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


def record_path(workspace_id: uuid.UUID) -> Path:
    return settings.pdf_dir / "packages" / f"{workspace_id}.json"


def has_record(workspace_id: uuid.UUID) -> bool:
    return record_path(workspace_id).is_file()


def read_record(workspace_id: uuid.UUID) -> bytes | None:
    """The screening record kept from an imported package, or None when the workspace has none."""
    path = record_path(workspace_id)
    return path.read_bytes() if path.is_file() else None


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
