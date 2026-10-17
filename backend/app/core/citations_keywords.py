"""Export keywords from a workspace (M40): its tags on each paper plus the screening decision (split out of
citations_export.py to keep that file small)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import tags
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit, WorkspaceSearchRun

STAGE1 = {"relevant": "screening: relevant", "not_relevant": "screening: not relevant"}
STAGE2 = {"include": "screening: included", "exclude": "screening: excluded"}


async def decisions(session: AsyncSession, ws: uuid.UUID) -> dict[uuid.UUID, str]:
    """paper id -> the workspace's latest screening decision: the full-text verdict when there is one, else the title
    and abstract one. Only this workspace's hits and runs count, never another workspace's verdict on the same paper."""
    found: dict[uuid.UUID, str] = {}
    hits = select(WorkspaceSearchHit.paper_id, WorkspaceSearchHit.stage1_status).where(
        WorkspaceSearchHit.workspace_id == ws,
        WorkspaceSearchHit.paper_id.is_not(None),
        WorkspaceSearchHit.stage1_status.in_(STAGE1),
    ).order_by(WorkspaceSearchHit.first_seen_at)  # fmt: skip
    for paper_id, status in await session.execute(hits):
        found[paper_id] = STAGE1[status]
    verdicts = (
        select(SearchRunEligibility.paper_id, SearchRunEligibility.stage2_status)
        .join(WorkspaceSearchRun, WorkspaceSearchRun.id == SearchRunEligibility.search_run_id)
        .where(WorkspaceSearchRun.workspace_id == ws, SearchRunEligibility.stage2_status.in_(STAGE2))
        .order_by(SearchRunEligibility.assessed_at.asc().nulls_first())
    )
    for paper_id, status in await session.execute(verdicts):
        found[paper_id] = STAGE2[status]
    return found


async def workspace_keywords(session: AsyncSession, ws: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    """paper id -> [tag names..., screening decision] for the papers that have any."""
    out = {pid: list(names) for pid, names in (await tags.paper_tag_map(session, ws)).items()}
    for pid, decision in (await decisions(session, ws)).items():
        out.setdefault(pid, []).append(decision)
    return out
