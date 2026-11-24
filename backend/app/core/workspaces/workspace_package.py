"""A workspace as one `.paperlab` file (M35a, D199): a zip holding the workspace, its papers' details (and their PDFs
when asked), tags, notes with their highlights and provenance, and a read-only screening record (`screening.json`, the
runs and every hit's decisions, with an AI suggestion marked `ai`, and `prisma.json`, the counts).

Inside the file papers are keyed `p1…pN` and runs `r1…rN`, never by database id. Nothing secret or local goes in: no
API key, connection, paper-source setting, contact email, file path or database id."""

import asyncio
import json
import logging
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import IO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.citations import citations_bundle_read
from app.core.citations.citations_bundle import SPOOL_BYTES
from app.core.search import prisma_export, search_run_results
from app.core.workspaces import tags, workspace_package_answers, workspace_package_screening, workspaces  # fmt: skip
from app.domain.errors import Conflict, NotFound
from app.models import Paper, Workspace
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


def _manifest(
    workspace: Workspace, members: list, note_views: list, pdf_files: list, answer_rows: list, answers_skipped: int
) -> dict:
    """The manifest.json record: format, versions, creation time, workspace fields and counts."""
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
    return manifest


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
    manifest = _manifest(workspace, members, note_views, pdf_files, answer_rows, answers_skipped)
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
# Two phases. Phase 1 finds each package paper's match in the library (free_copy.held_version may commit on its own, so
# nothing is written yet). Phase 2 writes the workspace, papers, tags and notes in one transaction; PDFs and the record
# file are written before its commit and removed if anything fails.

UNKNOWN_FORMAT = "package_unknown_format"
UNSAFE = "package_unsafe"
TOO_LARGE = "package_too_large"
TOO_LARGE_WITH_PDFS = "package_too_large_with_pdfs"  # an export that the import would refuse
INVALID = "package_invalid"
MAX_JSON_BYTES = 20 * 1024 * 1024
JSON_MEMBERS = ("manifest.json", "papers.json", "notes.json", "tags.json", "screening.json", "prisma.json")


def record_path(workspace_id: uuid.UUID) -> Path:
    return settings.pdf_dir / "packages" / f"{workspace_id}.json"


def has_record(workspace_id: uuid.UUID) -> bool:
    return record_path(workspace_id).is_file()


def read_record(workspace_id: uuid.UUID) -> bytes | None:
    """The screening record kept from an imported package, or None when the workspace has none."""
    path = record_path(workspace_id)
    return path.read_bytes() if path.is_file() else None


