"""The "Snowball next" list: go_further branches with a direction not yet snowballed, and a one-go runner."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import workspace_search
from app.core.branches import DIRECTIONS
from app.core.discovery import Providers
from app.core.hit_links import _runs, _seeds
from app.models import Paper
from app.models.provenance import WorkspaceBranchState
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit
from app.schemas.workspace_search import NextItem, SnowballOut


async def _titles(session: AsyncSession, hit_ids: list[uuid.UUID], paper_ids: list[uuid.UUID]) -> dict:
    out: dict = {}
    rows = await session.execute(
        select(WorkspaceSearchHit.id, ExternalRef.title, WorkspaceSearchHit.normalized_title)
        .outerjoin(ExternalRef, ExternalRef.id == WorkspaceSearchHit.external_ref_id)
        .where(WorkspaceSearchHit.id.in_(hit_ids))
    )
    out.update({hid: title or normalized for hid, title, normalized in rows})
    out.update((await session.execute(select(Paper.id, Paper.title).where(Paper.id.in_(paper_ids)))).all())
    return out


async def snowball_next(session: AsyncSession, workspace_id: uuid.UUID) -> list[NextItem]:
    """Directions count as run only when a seed's `done` says so, so a failed direction stays on the list."""
    done: dict[str, set[str]] = {}
    for seed, hit_id in _seeds(await _runs(session, workspace_id)):
        for key in {str(hit_id) if hit_id else None, seed.get("id")} - {None}:
            done.setdefault(key, set()).update(seed.get("done", []))
    rows = (await session.scalars(
        select(WorkspaceBranchState)
        .where(WorkspaceBranchState.workspace_id == workspace_id, WorkspaceBranchState.state == "go_further")
        .order_by(WorkspaceBranchState.updated_at, WorkspaceBranchState.id)
    )).all()
    titles = await _titles(session, [r.hit_id for r in rows if r.hit_id], [r.paper_id for r in rows if r.paper_id])
    items = []
    for row in rows:
        target = row.hit_id or row.paper_id
        left = [d for d in DIRECTIONS if d in row.directions and d not in done.get(str(target), set())]
        if left:
            items.append(NextItem(hit_id=row.hit_id, paper_id=row.paper_id, title=titles.get(target, ""), directions_left=left))
    return items


async def run_snowball_next(session: AsyncSession, providers: Providers, workspace_id: uuid.UUID) -> SnowballOut:
    """One snowball() call per distinct set of directions left; results summed."""
    groups: dict[tuple[str, ...], list[NextItem]] = {}
    for item in await snowball_next(session, workspace_id):
        groups.setdefault(tuple(item.directions_left), []).append(item)
    new_hits, skipped, errors = 0, [], {}
    for directions, items in groups.items():
        result = await workspace_search.snowball(
            session, providers, workspace_id,
            [i.paper_id for i in items if i.paper_id], [i.hit_id for i in items if i.hit_id],
            backward="cites" in directions, forward="cited_by" in directions,
        )
        new_hits += result.new_hits
        skipped += result.skipped_seeds
        errors.update(result.errors)
    return SnowballOut(new_hits=new_hits, skipped_seeds=skipped, errors=errors)
