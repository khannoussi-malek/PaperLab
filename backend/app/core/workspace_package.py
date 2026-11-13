"""A workspace as one `.paperlab` file (M35a, D199): a zip holding the workspace, its papers' details (and their PDFs
when asked), tags, notes with their highlights and provenance, and a read-only screening record (`screening.json`, the
runs and every hit's decisions, with an AI suggestion marked `ai`, and `prisma.json`, the counts).

Inside the file papers are keyed `p1…pN` and runs `r1…rN`, never by database id. Nothing secret or local goes in: no
API key, connection, paper-source setting, contact email, file path or database id."""

import asyncio
import json
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

from app.core import prisma_export, search_run_results, tags, workspaces
from app.core.citations_bundle import SPOOL_BYTES
from app.core.errors import NotFound
from app.models import Paper, Workspace
from app.models.references import ExternalRef
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit, WorkspaceSearchRun

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


def _paper_row(key: str, paper: Paper, pdf: str | None) -> dict:
    row = {"key": key, **{name: getattr(paper, name) for name in PAPER_FIELDS}, "has_pdf": paper.has_pdf}
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


def _ai_suggestion(hit: WorkspaceSearchHit) -> dict | None:
    if hit.suggestion is None:
        return None
    return {
        "ai": True, "suggestion": hit.suggestion, "reason": hit.suggestion_reason, "note": hit.suggestion_note,
        "model": hit.suggestion_model, "relevance": hit.suggestion_relevance, "confidence": hit.suggestion_confidence,
    }  # fmt: skip


async def _runs(session: AsyncSession, workspace_id: uuid.UUID) -> tuple[list[WorkspaceSearchRun], dict, dict]:
    """The workspace's runs in start order, their keys (r1…) and their display names."""
    query = select(WorkspaceSearchRun).where(WorkspaceSearchRun.workspace_id == workspace_id)
    runs = list((await session.scalars(query.order_by(WorkspaceSearchRun.started_at, WorkspaceSearchRun.id))).all())
    keys = {run.id: f"r{number}" for number, run in enumerate(runs, start=1)}
    return runs, keys, await search_run_results.run_labels(session, runs)


async def _screening_json(session: AsyncSession, workspace_id: uuid.UUID, runs, keys, labels, paper_keys) -> dict:
    # ponytail: every hit in memory at once; a workspace with hundreds of thousands of hits makes a large file.
    rows = await session.execute(
        select(
            WorkspaceSearchHit, ExternalRef.title, ExternalRef.doi,
            SearchRunEligibility.stage2_status, SearchRunEligibility.stage2_exclude_reason,
        )
        .outerjoin(ExternalRef, WorkspaceSearchHit.external_ref_id == ExternalRef.id)
        .outerjoin(
            SearchRunEligibility,
            (SearchRunEligibility.paper_id == WorkspaceSearchHit.paper_id)
            & (SearchRunEligibility.search_run_id == WorkspaceSearchHit.run_id),
        )
        .where(WorkspaceSearchHit.workspace_id == workspace_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
    )  # fmt: skip
    hits = [
        {
            "run": keys[hit.run_id],
            "title": title,
            "doi": doi,
            "paper": paper_keys.get(hit.paper_id),
            "source_method": hit.source_method,
            "stage1": {
                "status": hit.stage1_status,
                "exclude_reason": hit.stage1_exclude_reason,
                "note": hit.stage1_note,
            },
            "stage2": {"status": s2, "exclude_reason": s2_reason} if s2 is not None else None,
            "ai_suggestion": _ai_suggestion(hit),
        }
        for hit, title, doi, s2, s2_reason in rows
    ]
    run_rows = [
        {
            "key": keys[run.id],
            "query": labels[run.id],
            "sources": run.sources_json,
            "filters": run.filters_json,
            "status": run.status,
            "started_at": _iso(run.started_at),
        }
        for run in runs
    ]
    return {"runs": run_rows, "hits": hits}


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


async def export_package(session: AsyncSession, workspace_id: uuid.UUID, *, pdfs: bool) -> IO[bytes]:
    """The workspace as a zip file positioned at 0. Raises NotFound for an unknown workspace. With `pdfs`, each paper
    whose PDF is on disk is included; a paper whose PDF is missing is listed without one."""
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
    papers_json = {"papers": [
        _paper_row(keys[p.id], p, pdf_of[p.id][0] if p.id in pdf_of else None) for p in members
    ]}  # fmt: skip
    runs, run_keys, labels = await _runs(session, workspace_id)
    screening = await _screening_json(session, workspace_id, runs, run_keys, labels, keys)
    prisma = await _prisma_json(session, workspace_id, run_keys)
    note_views = await workspaces.notes(session, workspace_id)
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "paperlab_version": _paperlab_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": {name: getattr(workspace, name) for name in WORKSPACE_FIELDS},
        "counts": {"papers": len(members), "notes": len(note_views), "pdfs": len(pdf_files)},
    }
    parts = {
        "manifest.json": _dump(manifest),
        "papers.json": _dump(papers_json),
        "notes.json": _dump({"notes": _notes_json(note_views, keys)}),
        "tags.json": _dump({"tags": await _tags_json(session, workspace_id, keys)}),
        "screening.json": _dump(screening),
        "prisma.json": _dump(prisma),
    }
    return await asyncio.to_thread(_write, parts, pdf_files)
