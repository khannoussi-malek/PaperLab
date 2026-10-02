"""Screening assist for M30's stage 1 (M31): a ranking that learns from the reader's decisions, and (M31b) the
state of the local-model suggestion job. Suggest only: nothing here ever writes stage1_status."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm_connections
from app.core.errors import Conflict, NotFound
from app.core.screening_rank import Doc, rank, stop_hint
from app.core.workspace_search import _hit_out_dict
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit
from app.providers.llm import ANTHROPIC_HOST, host_of

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


CRITERIA_MAX_CHARS = 4000


async def _default_model(session: AsyncSession) -> tuple[str, bool, str] | None:
    """(label, is_local, host) of the default chat model, or None when there is none (spec §4.3)."""
    try:
        connection, model = await llm_connections.resolve(session, None)
    except Conflict:
        return None
    return (
        f"{connection.label} · {model.name}",
        llm_connections.is_local(connection.kind, connection.base_url),
        host_of(connection.base_url) if connection.base_url else ANTHROPIC_HOST,
    )


async def get_state(session: AsyncSession, workspace_id: uuid.UUID) -> dict:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound(f"workspace {workspace_id} not found")
    model = await _default_model(session)
    return {
        "criteria": workspace.screening_criteria,
        "ranked_used": workspace.screening_ranked_used,
        "suggest_status": workspace.suggest_status,
        "suggest_done": workspace.suggest_done,
        "suggest_total": workspace.suggest_total,
        "suggest_error": workspace.suggest_error,
        "model_label": model[0] if model else None,
        "model_is_local": model[1] if model else None,
        "model_host": model[2] if model else None,
    }


async def set_criteria(session: AsyncSession, workspace_id: uuid.UUID, criteria: str | None) -> dict:
    """Saves the workspace's criteria; a change clears every stored suggestion, judged against the old ones (§4.1)."""
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound(f"workspace {workspace_id} not found")
    if workspace.suggest_status != "idle":
        raise Conflict("Stop the suggestions before changing the criteria")
    criteria = (criteria or "").strip() or None
    if criteria != workspace.screening_criteria:
        workspace.screening_criteria = criteria
        await session.execute(
            update(WorkspaceSearchHit)
            .where(WorkspaceSearchHit.workspace_id == workspace_id)
            .values(suggestion=None, suggestion_reason=None, suggestion_note=None, suggestion_model=None,
                    suggested_at=None)
        )
    await session.commit()
    return await get_state(session, workspace_id)


def suggestion_queue(pool: Pool) -> list[uuid.UUID]:
    """Unscreened hits still without a suggestion and with some text to judge, in ranked order (§4.2)."""
    order, _ = ranked_order(pool)
    by_id = {hit.id: (hit, ref) for hit, ref in pool.rows}
    return [
        hit_id for hit_id in order
        if by_id[hit_id][0].suggestion is None and hit_text(*by_id[hit_id]).strip()
    ]


async def start_suggestions(session: AsyncSession, workspace_id: uuid.UUID, confirm_remote: bool) -> dict:
    """Marks the job running; the route enqueues it. Suggest only (D189): the job never writes stage1_status."""
    pool = await load_pool(session, workspace_id)
    workspace = pool.workspace
    if not workspace.screening_criteria:
        raise Conflict("Write the inclusion and exclusion criteria first")
    if workspace.suggest_status != "idle":
        raise Conflict("Suggestions are already running")
    model = await _default_model(session)
    if model is None:
        raise Conflict("no_model")
    label, local, host = model
    if not local and not confirm_remote:
        raise Conflict(f"Abstracts will be sent to {host} and may cost money")
    workspace.suggest_status = "running"
    workspace.suggest_done = 0
    workspace.suggest_total = len(suggestion_queue(pool))
    workspace.suggest_error = None
    await session.commit()
    return await get_state(session, workspace_id)


async def stop_suggestions(session: AsyncSession, workspace_id: uuid.UUID) -> dict:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound(f"workspace {workspace_id} not found")
    if workspace.suggest_status == "running":
        workspace.suggest_status = "stopping"  # the job reads this before each hit
        await session.commit()
    return await get_state(session, workspace_id)
