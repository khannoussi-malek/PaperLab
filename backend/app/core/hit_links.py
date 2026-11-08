"""Snowball tree: record each path a search hit reached a workspace by (workspace_hit_links)."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import WorkspaceHitLink
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

MAX_DEPTH = 50


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


async def already_found_by_saved_search(
    session: AsyncSession, run: WorkspaceSearchRun, hit_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Of these hits, the ones an earlier run of this run's saved search already linked as a search hit."""
    rows = await session.scalars(
        select(WorkspaceHitLink.child_hit_id)
        .join(WorkspaceSearchRun, WorkspaceSearchRun.id == WorkspaceHitLink.run_id)
        .where(
            WorkspaceHitLink.child_hit_id.in_(hit_ids), WorkspaceHitLink.kind == "search",
            WorkspaceSearchRun.saved_search_id == run.saved_search_id, WorkspaceSearchRun.id != run.id,
        )
    )
    return set(rows)


async def seed_parent(session: AsyncSession, workspace_id: uuid.UUID, paper_id: uuid.UUID) -> uuid.UUID | None:
    """The earliest hit in the workspace that carries this paper, if any."""
    return await session.scalar(
        select(WorkspaceSearchHit.id)
        .where(WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.paper_id == paper_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
        .limit(1)
    )


async def level_of(session: AsyncSession, hit_id: uuid.UUID) -> int:
    """How many hops a hit is from where it entered the workspace. Walks up breadth-first with a visited set (one
    query per depth), so a densely cross-linked graph costs one pass, not one per path. A hit with a `search` link
    is level 0 and not walked past; a link to a bare paper makes the hit one deeper than that paper; a hit with no
    links at all (legacy data) is level 0. No such hit within MAX_DEPTH: level 0."""
    best: int | None = None
    seen = {hit_id}
    frontier = [hit_id]
    for depth in range(MAX_DEPTH + 1):
        if not frontier or (best is not None and depth >= best):
            break
        rows = (await session.execute(
            select(
                WorkspaceHitLink.child_hit_id, WorkspaceHitLink.parent_hit_id,
                WorkspaceHitLink.parent_paper_id, WorkspaceHitLink.kind,
            ).where(WorkspaceHitLink.child_hit_id.in_(frontier))
        )).all()
        by_child: dict[uuid.UUID, list] = {h: [] for h in frontier}
        for row in rows:
            by_child[row.child_hit_id].append(row)
        nxt: list[uuid.UUID] = []
        for hit, links in by_child.items():
            if not links or any(link.kind == "search" for link in links):
                best = depth if best is None else min(best, depth)
                continue  # a root (or legacy hit): not walked past
            if any(link.parent_hit_id is None for link in links):  # a bare-paper parent counts as level 0
                best = depth + 1 if best is None else min(best, depth + 1)
            nxt.extend(
                p for link in links if (p := link.parent_hit_id) is not None and p not in seen and not seen.add(p)
            )
        frontier = nxt
    return best or 0
