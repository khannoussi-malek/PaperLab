"""Screening assist for M30's stage 1 (M31): a ranking that learns from the reader's decisions, and (M31b) the
state of the local-model suggestion job. Suggest only: nothing here ever writes stage1_status."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.screening_rank import Doc, rank, stop_hint
from app.core.workspace_search import _hit_out_dict
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit

RANKED_LIMIT_MAX = 500
_POSITIVE = {"relevant", "maybe"}


@dataclass(frozen=True)
class Pool:
    workspace: Workspace
    rows: list[tuple[WorkspaceSearchHit, ExternalRef | None]]  # found order: (first_seen_at, id)


async def load_pool(session: AsyncSession, workspace_id: uuid.UUID) -> Pool:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound(f"workspace {workspace_id} not found")
    query = (
        select(WorkspaceSearchHit, ExternalRef)
        .join(ExternalRef, WorkspaceSearchHit.external_ref_id == ExternalRef.id, isouter=True)
        .where(WorkspaceSearchHit.workspace_id == workspace_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
    )
    return Pool(workspace, [(hit, ref) for hit, ref in (await session.execute(query)).all()])


def hit_text(hit: WorkspaceSearchHit, ref: ExternalRef | None) -> str:
    """Title and abstract; a hit with no linked ref still has its normalized title."""
    if ref is None:
        return hit.normalized_title
    return f"{ref.title} {ref.abstract or ''}"


def _label(status: str | None) -> bool | None:
    return None if status is None else status in _POSITIVE


def ranked_order(pool: Pool) -> tuple[list[uuid.UUID], bool]:
    return rank([Doc(hit.id, hit_text(hit, ref), _label(hit.stage1_status)) for hit, ref in pool.rows])


async def ranked_hits(session: AsyncSession, workspace_id: uuid.UUID, limit: int) -> dict:
    pool = await load_pool(session, workspace_id)
    order, trained = ranked_order(pool)
    by_id = {hit.id: (hit, ref) for hit, ref in pool.rows}
    decided = sorted(
        (hit for hit, _ in pool.rows if hit.stage1_decided_at is not None and hit.stage1_status is not None),
        key=lambda hit: hit.stage1_decided_at,
        reverse=True,
    )
    hint = stop_hint([hit.stage1_status for hit in decided], len(pool.rows), trained)
    if trained and not pool.workspace.screening_ranked_used:
        pool.workspace.screening_ranked_used = True  # PRISMA reports the automation (spec §3.5)
        await session.commit()
    return {
        "items": [_hit_out_dict(*by_id[hit_id]) for hit_id in order[:limit]],
        "trained": trained,
        "total_unscreened": len(order),
        "streak": hint.streak,
        "threshold": hint.threshold,
        "show_stop_hint": hint.show,
    }
