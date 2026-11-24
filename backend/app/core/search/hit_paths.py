"""The paths from the search tree's roots down to one hit."""

import uuid
from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search.hit_provenance import _Edge, _graph, _runs
from app.domain.errors import NotFound
from app.models.workspace_search import WorkspaceSearchHit
from app.schemas.search_tree import ProvLink

PATHS_STEP_BUDGET = 10_000


async def paths_to(
    session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID, limit: int = 20
) -> list[list[ProvLink]]:
    """Every root-to-hit path, shortest first. Walks up from the hit over simple paths only (no repeated node).
    ponytail: the search stops after PATHS_STEP_BUDGET expansions, so a hit buried in a dense
    cross-linked graph may return fewer than `limit` paths."""
    owned = await session.scalar(select(WorkspaceSearchHit.id).where(
        WorkspaceSearchHit.id == hit_id, WorkspaceSearchHit.workspace_id == workspace_id))
    if owned is None:
        raise NotFound(f"hit {hit_id} not found")
    _, _, edges, _ = await _graph(session, workspace_id, {hit_id}, await _runs(session, workspace_id))
    above = defaultdict(list)
    for e in edges:
        above[e.child].append(e)
    found: list[tuple[_Edge, ...]] = []
    queue = deque([(str(hit_id), (), frozenset({str(hit_id)}))])
    for _ in range(PATHS_STEP_BUDGET):  # breadth-first over partial paths, so complete ones come out shortest first
        if not queue or len(found) >= limit:
            break
        node, tail, visited = queue.popleft()
        if not above[node]:
            found.append(tail)
        queue.extend((e.parent, (e, *tail), visited | {e.parent}) for e in above[node] if e.parent not in visited)
    return [
        [ProvLink(parent=e.parent, child=e.child, kind=e.kind, run_id=e.run_id, created_at=e.created_at) for e in p]
        for p in found
    ]
