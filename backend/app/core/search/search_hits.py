"""A run's hits: the paged list, one hit, and the owner's screening decisions on them."""

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search import ai_sort
from app.core.search.batch_fetch import _now
from app.core.search.branches import default_branch_on_decision
from app.core.workspaces import workspaces
from app.domain.errors import InvalidInput, NotFound
from app.domain.source_types import peer_reviewed_of
from app.models.references import ExternalRef
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit, WorkspaceSearchRun

if TYPE_CHECKING:
    from app.schemas.workspace_search import HitReviewUpdate


def _encode_cursor(first_seen_at: datetime, hit_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([first_seen_at.isoformat(), str(hit_id)]).encode()).decode()


_HIT_COLUMNS = [column.name for column in WorkspaceSearchHit.__table__.columns]


def _hit_out_dict(
    hit: WorkspaceSearchHit, ref: ExternalRef | None,
    stage2_status: str | None = None, stage2_exclude_reason: str | None = None,
) -> dict:
    """A hit's own columns plus its linked ExternalRef's title/authors/year/venue/doi/abstract/sources, merged into
    one dict for HitOut (I7). This codebase's models never use relationship() (a manual join/lookup is the
    convention), so the caller passes in whichever `ref` it already has — a join row here, an explicit
    session.get elsewhere — and this just does the merge, once, the same way for all three HitOut-producing call
    sites below.

    stage2_status/stage2_exclude_reason come from the hit's SearchRunEligibility row (paper_id, run_id), when one
    exists — only list_hits looks it up (the Screening tab drives off the list); review_hit/upload_hit_pdf are
    stage-1/acquisition mutations, not stage-2 actions, so they leave these at their None default rather than
    adding a fetch nothing reads."""
    data = {name: getattr(hit, name) for name in _HIT_COLUMNS}
    data.update(
        title=ref.title if ref else None,
        authors=ref.authors if ref else None,
        year=ref.year if ref else None,
        venue=ref.venue if ref else None,
        doi=ref.doi if ref else None,
        abstract=ref.abstract if ref else None,
        sources=ref.sources if ref else [],
        source_type=ref.source_type if ref else None,
        published_doi=ref.published_doi if ref else None,
        published_venue=ref.published_venue if ref else None,
        peer_review=peer_reviewed_of(ref.source_type if ref else None),
        stage2_status=stage2_status,
        stage2_exclude_reason=stage2_exclude_reason,
    )
    return data


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Raises InvalidInput for any malformed cursor — bad base64/UTF-8, bad JSON, wrong shape, or a
    seen_at/hit_id that don't parse as a datetime/UUID — so a tampered `after` value is a clean 422."""
    try:
        seen_at, hit_id = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(seen_at), uuid.UUID(hit_id)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise InvalidInput("invalid pagination cursor") from exc


async def list_hits(
    session: AsyncSession, workspace_id, limit: int = 50, after: str | None = None,
    stage1_status: str | None = None, acquisition_status: str | None = None, run_id: uuid.UUID | None = None,
    sort: str | None = None, min_relevance: int | None = None, suggested_only: bool = False,
    saved_search_id: uuid.UUID | None = None, found_after: datetime | None = None,
) -> tuple[list[dict], str | None]:
    """Keyset-paginated hit listing, ordered by (first_seen_at, id) so the cursor is stable even when several
    hits share a first_seen_at timestamp. `tuple_()` on both sides makes SQLAlchemy emit a real SQL row-value
    comparison (`WHERE (first_seen_at, id) > (:seen_at, :id)`) instead of a no-op Python tuple comparison.

    Outer-joins ExternalRef (I7) since external_ref_id is nullable — a hit with no linked ref still comes back,
    with title/authors/year/venue/doi all None via `_hit_out_dict`. Also outer-joins SearchRunEligibility on
    (paper_id, run_id) so the Screening tab (a later task) can drive its list off this same endpoint, filtered to
    acquisition_status IN ('imported', 'manual') — a hit with no stage-2 verdict yet still comes back, with
    stage2_status/stage2_exclude_reason None."""
    query = (
        select(WorkspaceSearchHit, ExternalRef, SearchRunEligibility)
        .join(ExternalRef, WorkspaceSearchHit.external_ref_id == ExternalRef.id, isouter=True)
        .join(
            SearchRunEligibility,
            (SearchRunEligibility.paper_id == WorkspaceSearchHit.paper_id)
            & (SearchRunEligibility.search_run_id == WorkspaceSearchHit.run_id),
            isouter=True,
        )
        .where(WorkspaceSearchHit.workspace_id == workspace_id)
    )
    if stage1_status == "undecided":
        query = query.where(WorkspaceSearchHit.stage1_status.is_(None))
    elif stage1_status:
        query = query.where(WorkspaceSearchHit.stage1_status == stage1_status)
    if suggested_only:
        query = query.where(WorkspaceSearchHit.suggestion.is_not(None))
    if run_id is not None:
        query = query.where(WorkspaceSearchHit.run_id == run_id)
    if saved_search_id is not None:  # the saved-search inbox (M7.6): hits its own runs found first
        runs = select(WorkspaceSearchRun.id).where(WorkspaceSearchRun.saved_search_id == saved_search_id)
        query = query.where(WorkspaceSearchHit.run_id.in_(runs))
    if found_after is not None:
        query = query.where(WorkspaceSearchHit.first_seen_at > found_after)
    if acquisition_status:
        query = query.where(WorkspaceSearchHit.acquisition_status == acquisition_status)
    if min_relevance is not None:
        if not 1 <= min_relevance <= 5:
            raise InvalidInput("min_relevance must be 1 to 5")
        query = query.where(WorkspaceSearchHit.suggestion_relevance >= min_relevance)
    if sort not in (None, "ai"):
        raise InvalidInput("sort must be 'ai' or empty")
    if sort == "ai":  # keyset cursor, see ai_sort
        if after:
            query = query.where(ai_sort.after_cursor(after))
        query = query.order_by(*ai_sort.AI_ORDER).limit(limit)
    else:
        if after:
            seen_at, hit_id = _decode_cursor(after)
            query = query.where(
                tuple_(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id) > tuple_(seen_at, hit_id)
            )
        query = query.order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id).limit(limit)
    rows = (await session.execute(query)).all()
    items = [
        _hit_out_dict(
            hit, ref,
            elig.stage2_status if elig else None, elig.stage2_exclude_reason if elig else None,
        )
        for hit, ref, elig in rows
    ]
    if len(rows) < limit:
        return items, None
    if sort == "ai":
        return items, ai_sort.encode_cursor(rows[-1][0])
    return items, _encode_cursor(rows[-1][0].first_seen_at, rows[-1][0].id)


async def get_hit(session: AsyncSession, hit_id, workspace_id) -> dict:
    hit = await session.get(WorkspaceSearchHit, hit_id)
    if hit is None or hit.workspace_id != workspace_id:
        raise NotFound(f"hit {hit_id} not found")
    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    return _hit_out_dict(hit, ref)


async def review_hit(session: AsyncSession, hit_id, workspace_id, update: "HitReviewUpdate") -> dict:
    """Stage-1 screening update for one hit. Scoped to workspace_id (same ownership rule as get_run/stop_run) so a
    hit_id guessed or leaked from another workspace can't be patched through this route."""
    await workspaces.require_writable(session, workspace_id)
    hit = await session.get(WorkspaceSearchHit, hit_id)
    if hit is None or hit.workspace_id != workspace_id:
        raise NotFound(f"hit {hit_id} not found")

    # The schema's model_validator only sees this request's own fields, not the hit's persisted state, so a
    # partial update that omits stage1_status (e.g. one that only nulls stage1_exclude_reason) can't be caught
    # there. Check the *effective* post-patch combination here instead.
    fields = update.model_fields_set
    new_status = update.stage1_status if "stage1_status" in fields else hit.stage1_status
    new_reason = update.stage1_exclude_reason if "stage1_exclude_reason" in fields else hit.stage1_exclude_reason
    if new_status == "not_relevant" and not new_reason:
        raise InvalidInput("stage1_exclude_reason is required when stage1_status is not_relevant")

    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(hit, field_name, value)
    if "stage1_status" in fields:
        # The stop hint's streak reads decisions by this time (M31 spec §3.2); an undone decision has none.
        hit.stage1_decided_at = _now() if hit.stage1_status is not None else None
        await default_branch_on_decision(session, workspace_id, [hit.id], hit.stage1_status)
    await session.commit()
    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    return _hit_out_dict(hit, ref)


async def bulk_review_hits(
    session: AsyncSession, workspace_id, hit_ids: list, stage1_status: str,
    stage1_exclude_reason: str | None, priority: int | None,
) -> int:
    """Applies the same stage1_status (and optional reason/priority) to every hit in hit_ids that belongs to
    workspace_id. Hit ids from another workspace are silently excluded from the count, not raised as an error —
    a bulk action naming one bad id shouldn't fail the whole batch."""
    await workspaces.require_writable(session, workspace_id)
    result = await session.execute(
        select(WorkspaceSearchHit).where(
            WorkspaceSearchHit.id.in_(hit_ids), WorkspaceSearchHit.workspace_id == workspace_id
        )
    )
    hits = result.scalars().all()
    decided_at = _now()  # one time for the whole batch
    for hit in hits:
        hit.stage1_status = stage1_status
        hit.stage1_decided_at = decided_at
        if stage1_exclude_reason:
            hit.stage1_exclude_reason = stage1_exclude_reason
        if priority is not None:
            hit.priority = priority
    await default_branch_on_decision(session, workspace_id, [h.id for h in hits], stage1_status)
    await session.commit()
    return len(hits)


async def owned_hit_ids(session: AsyncSession, workspace_id, hit_ids: list) -> set:
    """The ids among hit_ids that belong to workspace_id."""
    rows = await session.scalars(
        select(WorkspaceSearchHit.id).where(
            WorkspaceSearchHit.id.in_(hit_ids), WorkspaceSearchHit.workspace_id == workspace_id
        )
    )
    return set(rows)


async def clear_hits(session: AsyncSession, workspace_id: uuid.UUID) -> int:
    """Deletes every hit in the pool that hasn't been imported or manually acquired -- a clean-slate reset for a
    workspace whose accumulated search history no longer matters. Papers already pulled into the corpus are
    untouched (their hits are excluded from the delete, same as `import_hits`' own acquisition_status check).
    Run/cursor history is left alone too — this clears the pool a run FED, not the record that the run happened."""
    await workspaces.require_writable(session, workspace_id)
    result = await session.execute(
        delete(WorkspaceSearchHit).where(
            WorkspaceSearchHit.workspace_id == workspace_id,
            WorkspaceSearchHit.acquisition_status.notin_(["imported", "manual"]),
        )
    )
    await session.commit()
    return result.rowcount
