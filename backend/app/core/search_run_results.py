"""What each source did on a search run, in one shape for every caller (get_search_run, list_search_runs, the UI and
PRISMA). A run's `status` says the job ended; `outcome` and these results say whether the search actually reached its
sources: on 2026-11-02 six runs read "exhausted" with Semantic Scholar failing on all six and named on two."""

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.schemas.workspace_search import PrescreenCounts, SourceResult

# A source stuck on httpx errors retries this many times before its cursor is exhausted (workspace_search.py).
SOURCE_ERROR_CAP = 6
FAILED_STATES = ("gave_up", "cooling_down")

_HTTP_ERROR = re.compile(r"(?:Client|Server) error '(\d+)[^']*' for url 'https?://([^/']+)")


def short_error(text: str | None) -> str | None:
    """`HTTP 429 from api.crossref.org`, not httpx's message: its URL carries the contact email."""
    if not text:
        return None
    match = _HTTP_ERROR.search(text)
    return f"HTTP {match.group(1)} from {match.group(2)}" if match else text[:200]


def _state(cursor: WorkspaceSearchCursor, running: bool) -> str:
    stored = cursor.cursor_json or {}
    if cursor.exhausted:
        if stored.get("disabled"):
            return "disabled"
        return "gave_up" if stored.get("errors", 0) >= SOURCE_ERROR_CAP else "complete"
    if stored.get("errors"):
        return "cooling_down"
    return "paused" if stored.get("paused") or not running else "fetching"


def _reason(state: str, error: str | None, running: bool) -> str | None:
    if state == "gave_up":
        return f"Gave up after {SOURCE_ERROR_CAP} failed attempts: {error or 'no error recorded'}"
    if state == "cooling_down":
        waiting = "Waiting to retry" if running else "Was still waiting to retry when the run ended"
        return f"{waiting}: {error or 'no error recorded'}"
    if state == "paused":
        return "The run ended before this source finished; Continue fetches more."
    if state == "disabled":
        return "Turned off in Settings → Paper sources."
    return None


def source_results(
    run: WorkspaceSearchRun, cursors: Iterable[WorkspaceSearchCursor], limit: int = 200
) -> list[SourceResult]:
    stats = run.stats_json or {}
    running = run.status == "running"
    results = []
    for cursor in sorted(cursors, key=lambda c: c.source):
        state = _state(cursor, running)
        error = short_error(cursor.last_error)
        if state == "paused" and (cursor.cursor_json or {}).get("paused"):
            reason = f"Stopped at {limit} results for this pass; Continue fetches more."
        else:
            reason = _reason(state, error, running)
        results.append(SourceResult(
            source=cursor.source, state=state, reason=reason, last_error=error,
            raw_count=stats.get("per_source_raw_count", {}).get(cursor.source, 0),
            new_hits=stats.get("per_source_new_hits", {}).get(cursor.source, 0),
        ))
    return results


def outcome(status: str, results: list[SourceResult]) -> str:
    """`running` until the job ends, then `complete` only when every source ran dry."""
    if status == "running":
        return "running"
    return "complete" if all(r.state == "complete" for r in results) else "partial"


def failed_sources(run: WorkspaceSearchRun, results: list[SourceResult]) -> list[str]:
    """Every source that stopped answering, including one a run ended on before it used up its retries."""
    recorded = (run.stats_json or {}).get("failed_sources", [])
    return sorted({*recorded, *(r.source for r in results if r.state in FAILED_STATES)})


def searched(results: list[SourceResult]) -> tuple[list[str], list[str]]:
    """(searched, not searched) for PRISMA: a source that failed or was off and returned nothing was not searched."""
    missed = [r.source for r in results if r.raw_count == 0 and r.state in ("gave_up", "cooling_down", "disabled")]
    return [r.source for r in results if r.source not in missed], missed


async def cursors_by_run(
    session: AsyncSession, run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[WorkspaceSearchCursor]]:
    rows = await session.scalars(select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id.in_(run_ids)))
    found: dict[uuid.UUID, list[WorkspaceSearchCursor]] = {}
    for cursor in rows:
        found.setdefault(cursor.run_id, []).append(cursor)
    return found


async def prescreen_counts(session: AsyncSession, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, PrescreenCounts]:
    """Per run: hits a model judged, hits with a suggestion but no judgement (no usable abstract, or the model failed),
    and hits not reached yet. `suggest_done` counts the first two together."""
    hit = WorkspaceSearchHit
    not_judged = hit.suggestion_flags.contains(["no_abstract"]) | hit.suggestion_flags.contains(["model_error"])
    has_suggestion = hit.suggestion.is_not(None)
    rows = await session.execute(
        select(
            hit.run_id,
            func.count().filter(has_suggestion, ~not_judged),
            func.count().filter(has_suggestion, not_judged),
            func.count().filter(~has_suggestion),
        ).where(hit.run_id.in_(run_ids)).group_by(hit.run_id)
    )
    return {row[0]: PrescreenCounts(judged=row[1], not_judged=row[2], not_asked=row[3]) for row in rows.all()}
