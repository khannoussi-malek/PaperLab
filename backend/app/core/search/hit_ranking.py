"""Ranking a run's unscreened hits by how much they look like the ones the owner kept."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search.screening_rank import Doc, Features, features, rank, stop_hint
from app.core.search.search_hits import _hit_out_dict
from app.domain.errors import NotFound
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

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


@dataclass(frozen=True)
class _CachedFeatures:
    workspace_id: uuid.UUID
    ids: list[uuid.UUID]  # found order; any hit added or removed changes it
    abstracts: int  # an enrichment that fills an abstract changes it
    feats: Features


# ponytail: one workspace's features kept in memory (~220 MB at 276k hits), rebuilt (~13 s) whenever its hits or
# abstract count change, so a run still adding hits rebuilds on each call; tokenize only the new hits if that bites.
# An edited title alone is not noticed until the next change.
_feature_cache: _CachedFeatures | None = None
_feature_lock = asyncio.Lock()


def _pool_query(workspace_id: uuid.UUID, *text_columns):
    hit = WorkspaceSearchHit
    return (
        select(hit.id, hit.stage1_status, hit.stage1_decided_at, ExternalRef.abstract.is_not(None), *text_columns)
        .join(ExternalRef, hit.external_ref_id == ExternalRef.id, isouter=True)
        .where(hit.workspace_id == workspace_id)
        .order_by(hit.first_seen_at, hit.id)
    )


async def _pool_features(session: AsyncSession, workspace_id: uuid.UUID, rows: list) -> tuple[Features, list]:
    """The pool's features and the rows they match: the cached ones when `rows` still match them, else a fresh read
    of rows and text together (so a harvest landing between two reads can't misalign them)."""
    global _feature_cache
    ids, abstracts = [row[0] for row in rows], sum(row[3] for row in rows)
    cached = _feature_cache
    if cached and cached.workspace_id == workspace_id and cached.abstracts == abstracts and cached.ids == ids:
        return cached.feats, rows
    _feature_cache = None  # let the old pool go before building the next
    fresh = (await session.execute(_pool_query(
        workspace_id, WorkspaceSearchHit.normalized_title, ExternalRef.title, ExternalRef.abstract,
    ))).all()
    texts = [normalized if title is None else f"{title} {abstract or ''}"  # same text as hit_text()
             for *_, normalized, title, abstract in fresh]
    feats = await asyncio.to_thread(features, texts)
    _feature_cache = _CachedFeatures(workspace_id, [row[0] for row in fresh], sum(row[3] for row in fresh), feats)
    return feats, fresh


async def _inbox_ids(session: AsyncSession, saved_search_id: uuid.UUID, found_after: datetime | None) -> set[uuid.UUID]:
    """The hits a saved search's own runs found after `found_after` (M7.6 inbox)."""
    hit = WorkspaceSearchHit
    runs = select(WorkspaceSearchRun.id).where(WorkspaceSearchRun.saved_search_id == saved_search_id)
    query = select(hit.id).where(hit.run_id.in_(runs))
    if found_after is not None:
        query = query.where(hit.first_seen_at > found_after)
    return set(await session.scalars(query))


async def ranked_hits(
    session: AsyncSession, workspace_id: uuid.UUID, limit: int,
    saved_search_id: uuid.UUID | None = None, found_after: datetime | None = None,
) -> dict:
    """Reads only ids, decisions and (cached) features for the whole pool, and full rows for the `limit` shown:
    SE Creativity's 276k hits took 49 s as ORM rows, retrained on the event loop."""
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound(f"workspace {workspace_id} not found")
    rows = (await session.execute(_pool_query(workspace_id))).all()
    # One build or ranking at a time: two tabs opening at once build once, and each ranking of a big pool holds
    # ~300 MB of temporaries. ponytail: a second workspace waits behind a rebuild; per-workspace locks if that bites.
    async with _feature_lock:
        prebuilt = None
        if {_label(row[1]) for row in rows} >= {True, False}:  # rank() trains: it needs the features
            prebuilt, rows = await _pool_features(session, workspace_id, rows)
        docs = [Doc(row[0], "", _label(row[1])) for row in rows]
        order, trained = await asyncio.to_thread(rank, docs, prebuilt)
    decided = sorted(
        ((row[1], row[2]) for row in rows if row[2] is not None and row[1] is not None),
        key=lambda pair: pair[1],
        reverse=True,
    )
    hint = stop_hint([status for status, _ in decided], len(rows), trained)
    if trained and not workspace.screening_ranked_used:
        workspace.screening_ranked_used = True  # PRISMA reports the automation (spec §3.5)
        await session.commit()
    if saved_search_id is not None:  # the inbox in ranked order: trained on every decision, shown for its finds only
        inbox = await _inbox_ids(session, saved_search_id, found_after)
        order = [hit_id for hit_id in order if hit_id in inbox]
    shown = order[:limit]
    hit = WorkspaceSearchHit
    full = {
        h.id: (h, ref) for h, ref in (await session.execute(
            select(hit, ExternalRef).join(ExternalRef, hit.external_ref_id == ExternalRef.id, isouter=True)
            .where(hit.id.in_(shown))
        )).all()
    }
    return {
        "items": [_hit_out_dict(*full[hit_id]) for hit_id in shown if hit_id in full],  # cleared mid-request: dropped
        "trained": trained,
        "total_unscreened": len(order),
        "streak": hint.streak,
        "threshold": hint.threshold,
        "show_stop_hint": hint.show,
    }
