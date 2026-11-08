"""Snowball tree: record each path a search hit reached a workspace by (workspace_hit_links)."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import WorkspaceHitLink
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

MAX_DEPTH = 50

# Walks up through parent hits (cycle-safe via the depth cap). A node ends the walk when it has a search link, a
# link to a bare paper (that paper counts as level 0, so the node is level 1), or no links at all (legacy data,
# level 0). The level is the shallowest such node's depth plus its own level.
_LEVEL_SQL = text(
    """
    WITH RECURSIVE walk(hit_id, depth) AS (
        SELECT CAST(:hit_id AS uuid), 0
        UNION ALL
        SELECT l.parent_hit_id, w.depth + 1
        FROM walk w JOIN workspace_hit_links l ON l.child_hit_id = w.hit_id
        WHERE l.parent_hit_id IS NOT NULL AND w.depth < :max_depth
    )
    SELECT min(w.depth + CASE WHEN has_search THEN 0 WHEN has_paper_parent THEN 1 ELSE 0 END)
    FROM walk w
    CROSS JOIN LATERAL (
        SELECT coalesce(bool_or(kind = 'search'), false) AS has_search,
               coalesce(bool_or(parent_hit_id IS NULL AND kind <> 'search'), false) AS has_paper_parent,
               count(*) AS n
        FROM workspace_hit_links WHERE child_hit_id = w.hit_id
    ) f
    WHERE f.has_search OR f.has_paper_parent OR f.n = 0
    """
)


async def record_links(
    session: AsyncSession, run: WorkspaceSearchRun, child_hit_ids: list[uuid.UUID], kind: str,
    parent_hit_id: uuid.UUID | None, parent_paper_id: uuid.UUID | None,
) -> None:
    """One batched insert; a path already recorded is left alone. A hit is never linked to itself."""
    rows = [
        {
            "workspace_id": run.workspace_id, "child_hit_id": child, "parent_hit_id": parent_hit_id,
            "parent_paper_id": parent_paper_id, "run_id": run.id, "kind": kind,
        }
        for child in dict.fromkeys(child_hit_ids)
        if child != parent_hit_id
    ]
    if rows:
        await session.execute(pg_insert(WorkspaceHitLink).values(rows).on_conflict_do_nothing())


async def seed_parent(session: AsyncSession, workspace_id: uuid.UUID, paper_id: uuid.UUID) -> uuid.UUID | None:
    """The earliest hit in the workspace that carries this paper, if any."""
    return await session.scalar(
        select(WorkspaceSearchHit.id)
        .where(WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.paper_id == paper_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
        .limit(1)
    )


async def level_of(session: AsyncSession, hit_id: uuid.UUID) -> int:
    level = await session.scalar(_LEVEL_SQL, {"hit_id": hit_id, "max_depth": MAX_DEPTH})
    return 0 if level is None else level
