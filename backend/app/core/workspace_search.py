"""Fetch one page per source, merge and dedup against the library-outside pool, store new hits (M30a spec P2).

Reuses candidates.py's merge/dedup (`merge`, `_same_paper`, `normal_title`) exactly as the Find Papers flow
(`core/discovery.py`) does — a workspace search hit is a candidate that survived the same merge logic, stored
instead of returned. `search_batch()` takes a `WorkspaceSearchRun` row (not raw params) so a future cron-driven
caller (M7.6) can build one the same way this plan's worker does.
"""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.candidates import Candidate, from_arxiv, from_core, from_crossref, from_s2, from_work, merge, normal_title
from app.core.discovery import Providers
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import arxiv, core_ac, crossref, openalex, semantic_scholar

# Provider request page sizes. No source publishes a "max" beyond what its own search_page tests exercise, so
# these mirror discovery.py's PER_SOURCE ballpark, generous enough that most runs exhaust a source in one page.
PAGE_SIZE_BY_SOURCE = {"openalex": 100, "crossref": 30, "arxiv": 20, "core": 20, "semantic_scholar": 75}

_PAGE_FUNCS = {
    "arxiv": arxiv.search_page,
    "crossref": crossref.search_page,
    "core": core_ac.search_page,
    "semantic_scholar": semantic_scholar.search_page,
    "openalex": openalex.search_page,
}

# from_crossref returns None for a non-paper record (D73's Crossref filter); the other four mappers always
# return a Candidate. `is not None` below is a no-op for those four and the real filter for crossref.
_MAPPERS = {
    "arxiv": from_arxiv,
    "crossref": from_crossref,
    "core": from_core,
    "semantic_scholar": from_s2,
    "openalex": from_work,
}


@dataclass(frozen=True)
class BatchResult:
    new_hits: int
    sources_exhausted: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


async def _find_or_create_external_ref(session: AsyncSession, candidate: Candidate) -> ExternalRef:
    conditions = [
        column == value
        for value, column in (
            (candidate.doi, ExternalRef.doi),
            (candidate.arxiv_id, ExternalRef.arxiv_id),
            (candidate.s2_id, ExternalRef.s2_id),
            (candidate.openalex_id, ExternalRef.openalex_id),
            (candidate.core_id, ExternalRef.core_id),
        )
        if value
    ]
    existing = (
        (await session.execute(select(ExternalRef).where(or_(*conditions)))).scalars().first() if conditions else None
    )
    if existing is not None:
        for field_name in ("doi", "arxiv_id", "s2_id", "openalex_id", "core_id", "pdf_urls", "cited_by_count"):
            value = getattr(candidate, field_name, None)
            if value and not getattr(existing, field_name, None):
                setattr(existing, field_name, value)
        return existing
    ref = ExternalRef(
        title=candidate.title,
        doi=candidate.doi,
        arxiv_id=candidate.arxiv_id,
        s2_id=candidate.s2_id,
        openalex_id=candidate.openalex_id,
        core_id=candidate.core_id,
        authors=candidate.authors,
        year=candidate.year,
        venue=candidate.venue,
        cited_by_count=candidate.cited_by_count,
        pdf_urls=candidate.pdf_urls,
    )
    session.add(ref)
    await session.flush()
    return ref


async def search_batch(session: AsyncSession, providers: Providers, run: WorkspaceSearchRun) -> BatchResult:
    """One page per source in `run.sources_json`, merged and deduped, new hits stored. A source that fails (a
    provider's search_page raising httpx.HTTPError, same as discovery.py's existing search()) is recorded in
    `errors` and its cursor gets `last_error`; the run and its other sources are unaffected (spec P7)."""
    cursors = {
        c.source: c
        for c in (
            await session.execute(select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id))
        ).scalars()
    }

    found: dict[str, list[Candidate]] = {}
    errors: dict[str, str] = {}
    exhausted: list[str] = []

    for source in run.sources_json:
        cursor = cursors.get(source)
        if cursor is None or cursor.exhausted:
            continue
        client = providers.client(source)
        if client is None:
            continue
        try:
            raw_items, next_cursor = await _PAGE_FUNCS[source](
                client, run.query_text, PAGE_SIZE_BY_SOURCE[source], cursor.cursor_json.get("value", 0)
            )
        except httpx.HTTPError as exc:
            cursor.last_error = str(exc)
            errors[source] = str(exc)
            continue
        found[source] = [c for raw in raw_items if (c := _MAPPERS[source](raw)) is not None]
        cursor.last_error = None
        if next_cursor is None:
            cursor.exhausted = True
            exhausted.append(source)
        else:
            cursor.cursor_json = {"value": next_cursor}

    all_candidates = [c for group in found.values() for c in group]
    merged = merge(found, len(all_candidates)) if all_candidates else []

    new_hits = 0
    for candidate in merged:
        ref = await _find_or_create_external_ref(session, candidate)
        existing_hit = (
            (
                await session.execute(
                    select(WorkspaceSearchHit).where(
                        WorkspaceSearchHit.workspace_id == run.workspace_id,
                        WorkspaceSearchHit.external_ref_id == ref.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing_hit is not None:
            continue  # already in the pool (this run or an earlier one) — keeps its existing screening decision
        session.add(
            WorkspaceSearchHit(
                workspace_id=run.workspace_id,
                run_id=run.id,
                external_ref_id=ref.id,
                source_method="database_search",
                normalized_title=normal_title(candidate.title),
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        new_hits += 1

    return BatchResult(new_hits=new_hits, sources_exhausted=exhausted, errors=errors)


from app.core import workspaces
from app.core.errors import Conflict, InvalidInput, NotFound


async def start_run(
    session: AsyncSession, workspace_id, query_text: str, filters: dict, sources: list[str],
    query_overrides: dict | None = None, run_id=None,
) -> WorkspaceSearchRun:
    await workspaces.get(session, workspace_id)  # raises NotFound if missing
    if run_id is not None:
        run = await get_run(session, run_id)
        if run.workspace_id != workspace_id:
            raise NotFound(f"search run {run_id} not found")
        if run.status == "running":
            raise Conflict("search_run_already_running")
        run.status = "running"
        run.stopped_at = None
        await session.commit()
        return run

    run = WorkspaceSearchRun(
        workspace_id=workspace_id, query_text=query_text, filters_json=filters,
        query_overrides_json=query_overrides or {}, sources_json=sources, status="running",
        started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    for source in sources:
        session.add(WorkspaceSearchCursor(run_id=run.id, source=source, cursor_json={"value": 0}))
    await session.commit()
    return run


async def stop_run(session: AsyncSession, run_id, workspace_id=None) -> WorkspaceSearchRun:
    run = await get_run(session, run_id, workspace_id)
    run.status = "stopped"
    run.stopped_at = datetime.now(timezone.utc)
    await session.commit()
    return run


async def get_run(session: AsyncSession, run_id, workspace_id=None) -> WorkspaceSearchRun:
    run = await session.get(WorkspaceSearchRun, run_id)
    if run is None or (workspace_id is not None and run.workspace_id != workspace_id):
        raise NotFound(f"search run {run_id} not found")
    return run


def _encode_cursor(first_seen_at: datetime, hit_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([first_seen_at.isoformat(), str(hit_id)]).encode()).decode()


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
    stage1_status: str | None = None,
) -> tuple[list[WorkspaceSearchHit], str | None]:
    """Keyset-paginated hit listing, ordered by (first_seen_at, id) so the cursor is stable even when several
    hits share a first_seen_at timestamp. `tuple_()` on both sides makes SQLAlchemy emit a real SQL row-value
    comparison (`WHERE (first_seen_at, id) > (:seen_at, :id)`) instead of a no-op Python tuple comparison."""
    query = select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace_id)
    if stage1_status:
        query = query.where(WorkspaceSearchHit.stage1_status == stage1_status)
    if after:
        seen_at, hit_id = _decode_cursor(after)
        query = query.where(
            tuple_(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id) > tuple_(seen_at, hit_id)
        )
    query = query.order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id).limit(limit)
    hits = (await session.execute(query)).scalars().all()
    next_cursor = _encode_cursor(hits[-1].first_seen_at, hits[-1].id) if len(hits) == limit else None
    return hits, next_cursor
