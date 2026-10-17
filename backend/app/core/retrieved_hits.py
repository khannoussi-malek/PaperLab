"""Retrieved means retrieved (M67): a search hit left `failed` (no free PDF found) whose paper is in its workspace
anyway, added by Find papers, add_paper(s), an upload, the arXiv fallback or a dedup reuse, is `imported`, linked to
that paper, exactly as if import_hits had fetched it. It then leaves Get PDFs, enters full-text review and stops
counting as PRISMA "Not retrieved". Only hit bookkeeping changes; papers are never touched."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.candidates import normal_title
from app.models import Paper, workspace_papers
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit

# A title match also needs both years, within one (a preprint and its published version): an undated "Editorial"
# must not claim another.
YEAR_SLACK = 1


def _paper_keys(paper_id, doi, published_doi, openalex_id) -> list:
    return [paper_id, *(d.lower() for d in (doi, published_doi) if d), openalex_id]


def _hit_keys(hit: WorkspaceSearchHit, ref: ExternalRef | None) -> list:
    if ref is None:
        return [hit.paper_id]
    return [hit.paper_id, ref.imported_as, ref.doi and ref.doi.lower(), ref.openalex_id]


async def link(
    session: AsyncSession, workspace_id: uuid.UUID, paper_ids: list[uuid.UUID] | None = None
) -> list[uuid.UUID]:
    """Links the workspace's failed hits to the workspace papers (or only `paper_ids` among them) holding the same
    paper: by link (hit.paper_id, ref.imported_as), DOI, published DOI, OpenAlex id, or the hit's normalised title
    with both years known and within YEAR_SLACK. Returns the linked hit ids. Idempotent; the caller commits."""
    hits = (
        await session.execute(
            select(WorkspaceSearchHit, ExternalRef)
            .outerjoin(ExternalRef, ExternalRef.id == WorkspaceSearchHit.external_ref_id)
            .where(WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.acquisition_status == "failed")
        )
    ).all()
    if not hits:
        return []
    members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
    query = select(Paper.id, Paper.doi, Paper.published_doi, Paper.openalex_id, Paper.title, Paper.year)
    query = query.where(Paper.id.in_(members))
    if paper_ids is not None:
        query = query.where(Paper.id.in_(paper_ids))
    held: dict = {}
    by_title: dict[str, list[tuple[uuid.UUID, int | None]]] = {}
    for paper_id, doi, published_doi, openalex_id, title, year in (await session.execute(query)).all():
        for key in _paper_keys(paper_id, doi, published_doi, openalex_id):
            if key:
                held.setdefault(key, paper_id)
        if title:
            by_title.setdefault(normal_title(title), []).append((paper_id, year))

    linked = []
    for hit, ref in hits:
        year = ref.year if ref is not None else None
        dated = [
            pid
            for pid, y in by_title.get(hit.normalized_title, [])
            if None not in (y, year) and abs(y - year) <= YEAR_SLACK
        ]
        paper_id = next((held[k] for k in _hit_keys(hit, ref) if k and k in held), None) or next(iter(dated), None)
        if paper_id is None:
            continue
        hit.acquisition_status, hit.paper_id = "imported", paper_id
        if ref is not None and ref.imported_as is None:
            ref.imported_as = paper_id
        linked.append(hit.id)
    return linked


async def repair(session: AsyncSession) -> list[uuid.UUID]:
    """`link` across every workspace with a failed hit: the one-off fix for rows that went wrong before M67.
    Returns the linked hit ids; the caller commits (or rolls back, for a dry run)."""
    workspace_ids = (
        (
            await session.execute(
                select(WorkspaceSearchHit.workspace_id)
                .where(WorkspaceSearchHit.acquisition_status == "failed")
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return [hit_id for ws in workspace_ids for hit_id in await link(session, ws)]
