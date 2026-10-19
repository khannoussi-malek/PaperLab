"""Retrieved means retrieved (M67): a search hit left `failed` (no free PDF found) whose paper is in its workspace
anyway, added by Find papers, add_paper(s), an upload, the arXiv fallback or a dedup reuse, is `imported`, linked to
that paper, exactly as if import_hits had fetched it. It then leaves Get PDFs, enters full-text review and stops
counting as PRISMA "Not retrieved". Only hit bookkeeping (and the hit's tags, copied to the paper) changes; papers'
own data is never touched."""

import uuid
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import tags
from app.core.candidates import normal_title
from app.models import Paper, workspace_papers
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit

# A title match also needs both years, within one (a preprint and its published version): an undated "Editorial"
# must not claim another.
YEAR_SLACK = 1


class Linked(NamedTuple):
    hit_id: uuid.UUID
    paper_id: uuid.UUID
    rule: str  # "identifier" (a link, DOI, published DOI or OpenAlex id) or "title"


def _paper_keys(paper_id, doi, published_doi, openalex_id) -> list:
    return [paper_id, *(d.lower() for d in (doi, published_doi) if d), openalex_id]


def _hit_keys(hit: WorkspaceSearchHit, ref: ExternalRef | None) -> list:
    if ref is None:
        return [hit.paper_id]
    dois = [d.lower() for d in (ref.doi, ref.published_doi) if d]
    return [hit.paper_id, ref.imported_as, *dois, ref.external_ids.get("openalex")]


async def _held(session: AsyncSession, workspace_id: uuid.UUID):
    """The workspace's papers by identifier, and by normalised title."""
    members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
    query = select(Paper.id, Paper.doi, Paper.published_doi, Paper.openalex_id, Paper.title, Paper.year)
    # A paper saved without a PDF is not a retrieved one: its hit stays in "Get PDFs" (PRISMA, R6).
    query = query.where(Paper.id.in_(members), Paper.file_path.is_not(None))
    by_key: dict = {}
    by_title: dict[str, list[tuple[uuid.UUID, int | None]]] = {}
    for paper_id, doi, published_doi, openalex_id, title, year in (await session.execute(query)).all():
        for key in _paper_keys(paper_id, doi, published_doi, openalex_id):
            if key:
                by_key.setdefault(key, paper_id)
        if title:
            by_title.setdefault(normal_title(title), []).append((paper_id, year))
    return by_key, by_title


def _match(hit, ref, by_key, by_title) -> tuple[uuid.UUID, str] | None:
    if paper_id := next((by_key[k] for k in _hit_keys(hit, ref) if k and k in by_key), None):
        return paper_id, "identifier"
    year = ref.year if ref is not None else None
    same = by_title.get(hit.normalized_title, [])
    dated = {pid for pid, y in same if None not in (y, year) and abs(y - year) <= YEAR_SLACK}
    # Two papers of that title (LeCun 2015, Goodfellow 2016 "Deep Learning"): guessing could pick the wrong one.
    # ponytail: a title match made while only one of them is in the workspace stands; identifiers are the real fix.
    return (dated.pop(), "title") if len(dated) == 1 and len(same) == 1 else None


async def link(session: AsyncSession, workspace_id: uuid.UUID) -> list[Linked]:
    """Links the workspace's failed hits to the workspace paper holding the same paper: by link
    (hit.paper_id, ref.imported_as), DOI, published DOI or OpenAlex id, else by the hit's normalised title when exactly
    one paper has it, both years known and within YEAR_SLACK. Copies each linked hit's tags to its paper. A title
    match leaves the shared ExternalRef's `imported_as` alone, so no other workspace inherits a guess.
    Idempotent; the caller commits."""
    hits = (
        await session.execute(
            select(WorkspaceSearchHit, ExternalRef)
            .outerjoin(ExternalRef, ExternalRef.id == WorkspaceSearchHit.external_ref_id)
            .where(WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.acquisition_status == "failed")
        )
    ).all()
    if not hits:
        return []
    by_key, by_title = await _held(session, workspace_id)
    linked, done = [], []
    for hit, ref in hits:
        if (found := _match(hit, ref, by_key, by_title)) is None:
            continue
        paper_id, rule = found
        hit.acquisition_status, hit.paper_id = "imported", paper_id
        if rule == "identifier" and ref is not None and ref.imported_as is None:
            ref.imported_as = paper_id
        linked.append(Linked(hit.id, paper_id, rule))
        done.append(hit)
    await session.flush()
    await tags.apply_hit_tags(session, workspace_id, done)
    return linked


async def repair(session: AsyncSession) -> list[Linked]:
    """`link` across every workspace with a failed hit: the one-off fix for rows that went wrong before M67.
    The caller commits (or rolls back, for a dry run)."""
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
    return [found for ws in workspace_ids for found in await link(session, ws)]
