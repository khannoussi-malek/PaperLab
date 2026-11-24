"""Fetch one page per source, merge and dedup against the library-outside pool, store new hits (M30a spec P2).

Reuses candidates.py's merge/dedup (`merge`, `_same_paper`, `normal_title`) exactly as the Find Papers flow
(`core/search/discovery.py`) does — a workspace search hit is a candidate that survived the same merge logic, stored
instead of returned. `search_batch()` takes a `WorkspaceSearchRun` row (not raw params) so a future cron-driven
caller (M7.6) can build one the same way this plan's worker does.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers import paper_sources
from app.core.search import search_run_results, year_range
from app.core.search.source_registry import STARTING_CURSOR_VALUE as _STARTING_CURSOR_VALUE
from app.models.workspace_search import (
    SearchRunEligibility,
    WorkspaceSearchCursor,
    WorkspaceSearchHit,
    WorkspaceSearchRun,
)
from app.schemas.workspace_search import SearchRunOut, SearchRunSummary, SourceWarning

# Raw results one source may fetch in a single pass before it pauses (overshoot is at most one page). A paused
# source is not exhausted: continue_run resumes it from its next page.
PER_SOURCE_PASS_LIMIT = 200
# The search job's timeout (see workers/workspace_search.py); here so core (saved_searches) needn't import workers.
SEARCH_RUN_JOB_TIMEOUT = 1800


from app.core.papers import papers  # noqa: E402
from app.core.workspaces import workspaces  # noqa: E402
from app.domain.errors import Conflict, NotFound  # noqa: E402
from app.models import workspace_papers  # noqa: E402

# OpenAlex's `page` cursor is 1-based; every other source's is a 0-based offset (Task 2's convention — the
# engine tests' own START_CURSOR already knows this). Seeding OpenAlex at 0 asked its fake for a negative offset
# and got nothing back "by coincidence," hiding the bug (I4).

async def start_run(
    session: AsyncSession, workspace_id, query_text: str, filters: dict, sources: list[str],
    query_overrides: dict | None = None,
) -> WorkspaceSearchRun:
    await workspaces.require_writable(session, workspace_id)
    years = year_range.parse(filters)  # raises InvalidInput("invalid_years")
    filters = years.as_filters() if years else {}

    # D73's merge trust order (app/core/paper_sources.SOURCES) is what search_batch's `found` dict — insertion
    # ordered, fed straight into merge()'s ranking — relies on; storing sources in whatever order the caller sent
    # them silently let the caller's field order become the trust order instead.
    ordered_sources = [source for source in paper_sources.SOURCES if source in sources]
    warnings = paper_sources.search_warnings(await paper_sources.get(session), ordered_sources)

    run = WorkspaceSearchRun(
        workspace_id=workspace_id, query_text=query_text, filters_json=filters,
        query_overrides_json=query_overrides or {}, sources_json=ordered_sources, status="running",
        started_at=datetime.now(timezone.utc), stats_json={"warnings": warnings} if warnings else {},
    )
    session.add(run)
    await session.flush()
    for source in ordered_sources:
        seed = {"value": _STARTING_CURSOR_VALUE.get(source, 0)}
        session.add(WorkspaceSearchCursor(run_id=run.id, source=source, cursor_json=seed))
    await session.commit()
    return run


# What a new pass starts without: the pass's own counters and its end-of-pass flags. The totals (per_source_*,
# failed_sources) stay, so PRISMA and the run's history remain cumulative.
TRY_RUN_LOCK = text("SELECT pg_try_advisory_xact_lock(:key)")


def run_lock_key(run_id: uuid.UUID) -> int:
    """Postgres advisory locks take an int8/int4 key; a UUID is 128 bits, so this folds it down to 63 bits (fits
    a signed bigint). A hash collision only ever makes an unrelated run wait its turn — it can't corrupt data —
    so this doesn't need to be collision-proof."""
    return run_id.int & 0x7FFFFFFFFFFFFFFF


async def try_run_lock(session: AsyncSession, run_id: uuid.UUID) -> bool:
    """Non-blocking and transaction-scoped: released automatically on the next commit/rollback, so it only ever
    covers one batch iteration, not the whole run. False means another worker's iteration is already in flight
    for this run right now (e.g. a stop-then-immediate-restart race, since enqueue_job has no dedup job id) — the
    caller should back off instead of racing it to the same insert (I2)."""
    return bool(await session.scalar(TRY_RUN_LOCK, {"key": run_lock_key(run_id)}))


_PASS_STATS = ("cut_short", "unfinished_sources", "paused_sources")
_PASS_CURSOR_STATE = ("paused", "retry_after")


async def continue_run(session: AsyncSession, workspace_id, run_id) -> WorkspaceSearchRun:
    """Starts another pass over a stopped, cut-short, paused or failed run: every source that isn't exhausted
    picks up at its stored cursor, so no page is fetched twice. A source that gave up on errors is exhausted and
    stays out; the error count of a live one is kept, only its cooldown and pause are cleared."""
    await workspaces.require_writable(session, workspace_id)
    run = await get_run(session, run_id, workspace_id)
    if run.status == "running":
        raise Conflict("search_run_already_running")
    # A stopped job still mid-batch holds this lock until its commit; starting a pass now would race it.
    # Held only until the commit below (or the caller's rollback), so it never outlives this call.
    if not await try_run_lock(session, run.id):
        raise Conflict("search_run_still_stopping")
    live = (await session.scalars(
        select(WorkspaceSearchCursor).where(
            WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.exhausted.is_(False))
    )).all()
    if not live:
        raise Conflict("nothing_left_to_fetch")
    for cursor in live:
        cursor.cursor_json = {k: v for k, v in cursor.cursor_json.items() if k not in _PASS_CURSOR_STATE}
    kept = {k: v for k, v in run.stats_json.items() if k not in _PASS_STATS}
    run.stats_json = {**kept, "pass_raw_count": {}, "last_batch_new_hits": 0, "passes": kept.get("passes", 1) + 1}
    run.status = "running"
    run.stopped_at = None
    await session.commit()
    return run


async def sources_left(session: AsyncSession, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Each run's sources that still have results to fetch (cursor not exhausted); runs with none are absent."""
    rows = await session.execute(
        select(WorkspaceSearchCursor.run_id, WorkspaceSearchCursor.source)
        .where(WorkspaceSearchCursor.run_id.in_(run_ids), WorkspaceSearchCursor.exhausted.is_(False))
        .order_by(WorkspaceSearchCursor.source)
    )
    left: dict[uuid.UUID, list[str]] = {}
    for run_id, source in rows.all():
        left.setdefault(run_id, []).append(source)
    return left


async def _reports(session: AsyncSession, runs: list[tuple[WorkspaceSearchRun, int]]) -> dict[uuid.UUID, dict]:
    """The fields get_search_run and list_search_runs both return, per run."""
    run_ids = [run.id for run, _ in runs]
    cursors = await search_run_results.cursors_by_run(session, run_ids)
    prescreen = await search_run_results.prescreen_counts(session, run_ids)
    reports = {}
    for run, hit_count in runs:
        results = search_run_results.source_results(run, cursors.get(run.id, []), PER_SOURCE_PASS_LIMIT)
        reports[run.id] = {
            "hit_count": hit_count,
            "per_source_raw_count": (run.stats_json or {}).get("per_source_raw_count", {}),
            "failed_sources": search_run_results.failed_sources(run, results),
            "source_results": results,
            "outcome": search_run_results.outcome(run.status, results),
            "warnings": [SourceWarning(**w) for w in (run.stats_json or {}).get("warnings", [])],
            **({"prescreen": prescreen[run.id]} if run.id in prescreen else {}),
            "snowball": (run.stats_json or {}).get("snowball"),
        }
    return reports


async def run_out(session: AsyncSession, run: WorkspaceSearchRun) -> SearchRunOut:
    hit_count = await session.scalar(
        select(func.count()).select_from(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id)
    )
    left = await sources_left(session, [run.id])
    report = (await _reports(session, [(run, hit_count or 0)]))[run.id]
    label = (await search_run_results.run_labels(session, [run]))[run.id]
    return SearchRunOut.model_validate(run).model_copy(update={"query_text": label}).with_report(left.get(run.id, []), report)


async def run_summaries(
    session: AsyncSession, rows: list[tuple[WorkspaceSearchRun, int]]
) -> list[SearchRunSummary]:
    left = await sources_left(session, [run.id for run, _ in rows])
    reports = await _reports(session, rows)
    labels = await search_run_results.run_labels(session, [run for run, _ in rows])
    return [SearchRunSummary.from_run(run, left.get(run.id, []), reports[run.id], labels[run.id]) for run, _ in rows]


async def stop_run(session: AsyncSession, run_id, workspace_id=None) -> WorkspaceSearchRun:
    run = await get_run(session, run_id, workspace_id)
    await workspaces.require_writable(session, run.workspace_id)
    if run.status != "running":
        # Stopping only applies to a run that's actually in flight — same "doesn't apply to the current state"
        # convention as start_run's own Conflict above, not a silent no-op that could paper over a stale double
        # click.
        raise Conflict("search_run_not_running")
    run.status = "stopped"
    run.stopped_at = datetime.now(timezone.utc)
    await session.commit()
    return run


async def get_run(session: AsyncSession, run_id, workspace_id=None) -> WorkspaceSearchRun:
    run = await session.get(WorkspaceSearchRun, run_id)
    if run is None or (workspace_id is not None and run.workspace_id != workspace_id):
        raise NotFound(f"search run {run_id} not found")
    return run


async def list_runs(
    session: AsyncSession, workspace_id: uuid.UUID, limit: int = 20
) -> list[tuple[WorkspaceSearchRun, int]]:
    """A workspace's runs, newest first, each with the number of hits it added."""
    rows = await session.execute(
        select(WorkspaceSearchRun, func.count(WorkspaceSearchHit.id))
        .outerjoin(WorkspaceSearchHit, WorkspaceSearchHit.run_id == WorkspaceSearchRun.id)
        .where(WorkspaceSearchRun.workspace_id == workspace_id)
        .group_by(WorkspaceSearchRun.id)
        .order_by(WorkspaceSearchRun.started_at.desc())
        .limit(limit)
    )
    return [(run, count) for run, count in rows.all()]


NEEDS_FULL_TEXT = "This paper has no PDF yet, so its full text can't be assessed."


async def set_eligibility(
    session: AsyncSession, workspace_id: uuid.UUID, paper_id: uuid.UUID, run_id: uuid.UUID,
    status: str, exclude_reason: str | None,
) -> SearchRunEligibility:
    """Upserts one (paper_id, run_id) stage-2 verdict in a single INSERT ... ON CONFLICT DO UPDATE, insert on the
    first PATCH, update in place on a later one for the same pair. A `session.get` then conditional `session.add`
    (the previous approach) has a race window between the SELECT and the write where two concurrent PATCHes for
    the same pair can both see no row and both try to insert — one loses to a duplicate-PK IntegrityError. A
    single upsert statement closes that window, same discipline as `_insert_hit`'s upsert above, on this table's
    own (paper_id, search_run_id) composite PK. Same ownership discipline as review_hit/get_run — confirms both
    the run (get_run, which already raises NotFound on a workspace mismatch or missing run) and the paper
    (workspace_papers membership, same check snowball() above uses) belong to workspace_id before writing."""
    await workspaces.require_writable(session, workspace_id)
    await get_run(session, run_id, workspace_id)
    member = (await session.execute(
        select(workspace_papers.c.paper_id).where(
            workspace_papers.c.workspace_id == workspace_id, workspace_papers.c.paper_id == paper_id
        )
    )).first()
    if member is None:
        raise NotFound(f"paper {paper_id} not in workspace {workspace_id}")
    if not (await papers.get_paper(session, paper_id)).has_pdf:  # R9: no full text, nothing to assess
        raise Conflict("needs_full_text", detail=NEEDS_FULL_TEXT)

    assessed_at = datetime.now(timezone.utc)
    stmt = (
        pg_insert(SearchRunEligibility)
        .values(
            paper_id=paper_id, search_run_id=run_id, stage2_status=status,
            stage2_exclude_reason=exclude_reason, assessed_at=assessed_at,
        )
        .on_conflict_do_update(
            index_elements=["paper_id", "search_run_id"],
            set_={"stage2_status": status, "stage2_exclude_reason": exclude_reason, "assessed_at": assessed_at},
        )
        .returning(SearchRunEligibility)
        # populate_existing: an UPDATE branch's RETURNING row must overwrite an already-identity-mapped instance
        # (e.g. this same (paper_id, run_id) loaded earlier in this session) with the fresh DB values — without
        # it, the ORM leaves an already-loaded object's attributes as they were and the caller sees stale data.
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).scalar_one()
    await session.commit()
    return row


