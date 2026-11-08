"""Branch decisions for the snowball tree: "go further" or "stopped" per hit or paper. No row means undecided."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidInput, NotFound
from app.models import workspace_papers
from app.models.provenance import WorkspaceBranchState
from app.models.workspace_search import WorkspaceSearchHit
from app.schemas.workspace_search import BranchOut

DIRECTIONS = ("cites", "cited_by")
STATES = ("go_further", "stopped")
REASON_MAX = 200


def _validate(hit_id, paper_id, state, directions, reason) -> list[str]:
    """Raises InvalidInput for a bad request; returns the directions de-duplicated, in DIRECTIONS order."""
    if (hit_id is None) == (paper_id is None):
        raise InvalidInput("give exactly one of hit_id and paper_id")
    if state is not None and state not in STATES:
        raise InvalidInput(f"state must be one of {', '.join(STATES)}")
    if bad := [d for d in directions if d not in DIRECTIONS]:
        raise InvalidInput(f"unknown direction: {bad[0]!r}")
    ordered = [d for d in DIRECTIONS if d in directions]
    if state == "go_further" and not ordered:
        raise InvalidInput("go_further needs at least one direction")
    if reason is not None and len(reason) > REASON_MAX:
        raise InvalidInput(f"reason is longer than {REASON_MAX} characters")
    return ordered


async def _check_target(session: AsyncSession, workspace_id, hit_id, paper_id) -> None:
    if hit_id is not None:
        hit = await session.get(WorkspaceSearchHit, hit_id)
        if hit is None or hit.workspace_id != workspace_id:
            raise NotFound(f"hit {hit_id} not found")
        return
    member = (await session.execute(
        select(workspace_papers.c.paper_id).where(
            workspace_papers.c.workspace_id == workspace_id, workspace_papers.c.paper_id == paper_id
        )
    )).first()
    if member is None:
        raise NotFound(f"paper {paper_id} not in workspace {workspace_id}")


async def set_branch(
    session: AsyncSession, workspace_id: uuid.UUID, *, hit_id: uuid.UUID | None = None,
    paper_id: uuid.UUID | None = None, state: str | None, directions: list[str], reason: str | None,
) -> BranchOut:
    """state=None deletes the decision (undecided). The reason is kept only for "stopped"; directions only for
    "go_further"."""
    ordered = _validate(hit_id, paper_id, state, directions, reason)
    await _check_target(session, workspace_id, hit_id, paper_id)
    if state is None:
        await session.execute(delete(WorkspaceBranchState).where(
            WorkspaceBranchState.workspace_id == workspace_id,
            WorkspaceBranchState.hit_id.is_not_distinct_from(hit_id),
            WorkspaceBranchState.paper_id.is_not_distinct_from(paper_id),
        ))
        await session.commit()
        return BranchOut(hit_id=hit_id, paper_id=paper_id, state=None, directions=[], reason=None)
    values = {
        "state": state,
        "set_by": "owner",
        "directions": ordered if state == "go_further" else [],
        "reason": reason if state == "stopped" else None,
    }
    await session.execute(
        pg_insert(WorkspaceBranchState)
        .values(workspace_id=workspace_id, hit_id=hit_id, paper_id=paper_id, **values)
        .on_conflict_do_update(
            constraint="uq_workspace_branch_states_target", set_={**values, "updated_at": datetime.now(timezone.utc)}
        )
    )
    await session.commit()
    return BranchOut(hit_id=hit_id, paper_id=paper_id, **{k: v for k, v in values.items() if k != "set_by"})


async def default_branch_on_decision(
    session: AsyncSession, workspace_id: uuid.UUID, hit_ids: list[uuid.UUID], stage1_status: str | None
) -> None:
    """Screening's default follows the decision: relevant -> go further both ways, not_relevant -> stopped, undone
    (None) -> no row. Only rows set_by 'screening' are touched, so a hand choice is never overwritten or removed.
    Ignores hits outside the workspace; does not commit (the caller does). Any other status ('maybe') is a no-op."""
    if not hit_ids or stage1_status not in ("relevant", "not_relevant", None):
        return
    owned = (await session.scalars(select(WorkspaceSearchHit.id).where(
        WorkspaceSearchHit.id.in_(hit_ids), WorkspaceSearchHit.workspace_id == workspace_id
    ))).all()
    if not owned:
        return
    if stage1_status is None:
        await session.execute(delete(WorkspaceBranchState).where(
            WorkspaceBranchState.workspace_id == workspace_id, WorkspaceBranchState.hit_id.in_(owned),
            WorkspaceBranchState.set_by == "screening",
        ))
        return
    state = "go_further" if stage1_status == "relevant" else "stopped"
    values = {"state": state, "directions": list(DIRECTIONS) if state == "go_further" else [], "reason": None}
    insert = pg_insert(WorkspaceBranchState).values([
        {"workspace_id": workspace_id, "hit_id": h, "set_by": "screening", **values} for h in owned
    ])
    await session.execute(insert.on_conflict_do_update(
        constraint="uq_workspace_branch_states_target", set_={**values, "updated_at": datetime.now(timezone.utc)},
        where=WorkspaceBranchState.set_by == "screening",
    ))
