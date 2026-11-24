"""One fetch pass of a search run: ask each source for its next page, store new candidates as hits, back off a
failing source."""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search import hit_links, search_run_results, year_range
from app.core.search.candidates import merge, normal_title
from app.core.search.source_clients import Providers
from app.core.search.source_registry import MAPPERS as _MAPPERS
from app.core.search.source_registry import PAGE_FUNCS as _PAGE_FUNCS
from app.core.search.source_registry import PAGE_SIZE_BY_SOURCE
from app.domain.candidates import Candidate
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun

# A source stuck on httpx errors (spec §16: unauthenticated S2 search 429s by default) retries this many times
# before its cursor is marked exhausted instead of spinning forever (C2 part 1) — small enough that a real outage
# still lets the run finish on its other sources well inside a job's lifetime.
#
# Retries are spaced out (below), not consecutive: without spacing, all SOURCE_ERROR_CAP attempts land within a
# few seconds of each other (one worker-loop pacing interval apart, BATCH_PACING_SECONDS in
# workers/workspace_search.py), so a source that's just having a brief, transient blip — arXiv's own API answers
# a plain 406 every so often for no discernible reason, confirmed by re-running an identical, otherwise-successful
# request seconds later — gets abandoned for the rest of the run before the blip could ever clear. Growing
# cooldowns give a real chance for that, while a source that's persistently broken (an unauthenticated S2/CORE
# 429, expected by default per spec §16) still gives up for good once every backoff step is spent.
SOURCE_ERROR_CAP = search_run_results.SOURCE_ERROR_CAP


_ERROR_BACKOFF_SECONDS = (10, 30, 90, 180, 300)


@dataclass(frozen=True)
class BatchResult:
    new_hits: int
    sources_exhausted: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    # Per-source raw item counts for this one batch, pre-merge/pre-dedup — spec §5/§13 wants these for M30b's
    # PRISMA "identified" number, which can't be reconstructed later once a run is exhausted (I1). The worker
    # accumulates these into run.stats_json across iterations; search_batch itself stays stateless.
    raw_counts: dict[str, int] = field(default_factory=dict)
    out_of_range: dict[str, int] = field(default_factory=dict)  # M39 F2: dropped by the run's year range (D221)
    new_by_source: dict[str, int] = field(default_factory=dict)  # a paper two sources found counts for both
    asked: bool = False  # False: every source was cooling down, paused or done, so this pass fetched nothing


@dataclass(frozen=True)
class HitOrigin:
    """How new hits were reached: a database search, or one snowball hop from a seed (a hit, or a bare paper)."""

    source_method: str = "database_search"
    kind: str = "search"  # the workspace_hit_links kind: search, cites or cited_by
    seed_paper_id: uuid.UUID | None = None
    snowball_round: int | None = None
    parent_hit_id: uuid.UUID | None = None
    parent_paper_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Stored:
    new_hits: int
    hit_ids: list[uuid.UUID]  # every hit the candidates resolved to, new and existing
    new_by_source: dict[str, int]  # a paper two sources found counts for both


async def _best_match(session: AsyncSession, candidate: Candidate) -> ExternalRef | None:
    """The stored reference sharing an identifier with the candidate, a DOI match first.

    The OR-match can hit more than one row (e.g. one row shares the candidate's DOI, a different row shares its
    semantic_scholar id) — `.first()` on an unordered result would pick one arbitrarily, and a wrong pick doesn't
    just risk a bad backfill, it attaches this hit to the wrong paper outright (Important 2 from the fix-round
    review: a candidate importable later would then download/attach the WRONG row's PDF). DOI is the strongest
    identifier, so when the candidate has one, a DOI-matching row is ordered first — ties among several DOI matches
    (shouldn't happen; doi has no DB-level uniqueness) or candidates with no DOI fall back to whatever order the DB
    happens to return, same as before."""
    conditions = [
        ExternalRef.external_ids[source].astext == value for source, value in candidate.external_ids.items()
    ]
    if candidate.doi:
        conditions.append(ExternalRef.doi == candidate.doi)
    if not conditions:
        return None
    query = select(ExternalRef).where(or_(*conditions))
    if candidate.doi:
        # `.is_(True)` turns a NULL-doi row's comparison (SQL NULL, not FALSE) into a definite boolean first —
        # otherwise Postgres' NULLS-FIRST-on-DESC default would rank a no-DOI row above an actual DOI match.
        query = query.order_by((ExternalRef.doi == candidate.doi).is_(True).desc())
    return (await session.execute(query)).scalars().first()


async def _owned_elsewhere(session: AsyncSession, owns, ref: ExternalRef) -> bool:
    """Another reference row already holds this identifier (`owns` is the column condition)."""
    return await session.scalar(select(ExternalRef.id).where(owns, ExternalRef.id != ref.id)) is not None


async def _backfill_ids(session: AsyncSession, existing: ExternalRef, candidate: Candidate) -> None:
    """Gives the matched row the candidate's identifiers it lacks, each only when no OTHER row already owns it:
    otherwise it either violates the partial unique indexes on external_ids->>'openalex'/'semantic_scholar'
    (Phase 0b), or — for doi/arxiv/core, which have no DB uniqueness — silently mis-attributes an identifier to
    the wrong paper (spec review I3; this exact mechanism corrupted a real row once, see the ledger's "Closed
    Access Fixture" incident)."""
    external_ids = dict(existing.external_ids)
    for source, value in candidate.external_ids.items():
        if source in external_ids:
            continue  # `existing` already has its own value for this source
        if not await _owned_elsewhere(session, ExternalRef.external_ids[source].astext == value, existing):
            external_ids[source] = value
    if external_ids != existing.external_ids:
        existing.external_ids = external_ids
    if candidate.doi and not existing.doi:
        if not await _owned_elsewhere(session, ExternalRef.doi == candidate.doi, existing):
            existing.doi = candidate.doi


def _backfill_fields(existing: ExternalRef, candidate: Candidate) -> None:
    """Fills the matched row's empty fields from the candidate. `pdf_urls` only crosses over when the row's own DOI
    doesn't contradict the candidate's, so a match found only via a weaker/shared identifier never hands one paper's
    PDF link to a different paper."""
    if candidate.pdf_urls and not existing.pdf_urls:
        doi_conflict = existing.doi and candidate.doi and existing.doi != candidate.doi
        if not doi_conflict:
            existing.pdf_urls = candidate.pdf_urls
    for name in ("cited_by_count", "abstract", "source_type", "published_doi", "published_venue"):
        if getattr(candidate, name) and not getattr(existing, name):
            setattr(existing, name, getattr(candidate, name))
    # Union, not backfill-if-empty like the fields above: a later search or snowball round can rediscover an
    # already-known paper through a source that hadn't found it before, and every one of those is worth
    # keeping, not just whichever happened to create the row.
    if candidate.sources:
        existing.sources = list(dict.fromkeys([*existing.sources, *candidate.sources]))


async def _new_ref(session: AsyncSession, candidate: Candidate) -> ExternalRef:
    ref = ExternalRef(
        title=candidate.title,
        doi=candidate.doi,
        external_ids=dict(candidate.external_ids),
        authors=candidate.authors,
        year=candidate.year,
        venue=candidate.venue,
        cited_by_count=candidate.cited_by_count,
        abstract=candidate.abstract,
        pdf_urls=candidate.pdf_urls,
        sources=list(candidate.sources),
        source_type=candidate.source_type,
        published_doi=candidate.published_doi,
        published_venue=candidate.published_venue,
    )
    session.add(ref)
    await session.flush()
    return ref


async def _find_or_create_external_ref(
    session: AsyncSession, candidate: Candidate, *, backfill: bool = True
) -> ExternalRef:
    """The candidate's reference row: the best stored match, given what it lacks from the candidate, or a new one."""
    existing = await _best_match(session, candidate)
    if existing is None:
        return await _new_ref(session, candidate)
    if backfill:  # a package import only reads a library reference; it never edits one (M35c M1)
        await _backfill_ids(session, existing, candidate)
        _backfill_fields(existing, candidate)
    return existing


def _now() -> datetime:
    """A thin wrapper around datetime.now(timezone.utc), so a test can monkeypatch just this module's own clock
    reads for the error-backoff check below without needing a real sleep — same reasoning as
    workers/workspace_search.py's own _now() wrapper (that one for a wall-clock deadline, this one for a
    per-source retry cooldown)."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Page:
    """One source's turn in a pass."""

    asked: bool = False
    found: list[Candidate] | None = None  # None: nothing fetched
    error: str | None = None
    exhausted: bool = False
    raw: int = 0  # raw items, minus the ones the run's year range dropped
    out_of_range: int = 0


def _due(cursor: WorkspaceSearchCursor | None, now: datetime) -> bool:
    if cursor is None or cursor.exhausted or cursor.cursor_json.get("paused"):
        return False
    retry_after = cursor.cursor_json.get("retry_after")
    # Cooling down from a recent error — not a failure, not exhausted, just not due yet.
    return not (retry_after and now < datetime.fromisoformat(retry_after))


def _disabled(cursor: WorkspaceSearchCursor) -> _Page:
    """Disabled/unconfigured (e.g. Unpaywall with no contact_email — the fresh-database default): nothing to fetch
    here, not an error. Marked exhausted now so the worker's all(c.exhausted ...) check can still become true once
    every other source has genuinely exhausted (M30a Task 17 E2E bug)."""
    cursor.last_error = None
    cursor.exhausted = True
    cursor.cursor_json = {**cursor.cursor_json, "disabled": True}
    return _Page(exhausted=True)


def _failed(cursor: WorkspaceSearchCursor, exc: httpx.HTTPError, now: datetime) -> _Page:
    """Bounded retry (C2 part 1): a source stuck on httpx errors (e.g. an unauthenticated S2 429 — the default case
    per spec §16's spike, not an edge case) must eventually stop retrying instead of spinning until the worker's
    job_timeout kills it mid-commit. Spaced out (see SOURCE_ERROR_CAP's comment), not consecutive, so a
    brief/transient error gets a real chance to clear before the source is abandoned for the rest of the run."""
    message = str(exc) or type(exc).__name__  # a timeout's own text is empty
    cursor.last_error = message
    error_count = cursor.cursor_json.get("errors", 0) + 1
    if error_count >= SOURCE_ERROR_CAP:
        cursor.exhausted = True
        cursor.cursor_json = {**cursor.cursor_json, "errors": error_count}
        return _Page(asked=True, error=message, exhausted=True)
    backoff = _ERROR_BACKOFF_SECONDS[min(error_count - 1, len(_ERROR_BACKOFF_SECONDS) - 1)]
    retry_after = (now + timedelta(seconds=backoff)).isoformat()
    cursor.cursor_json = {**cursor.cursor_json, "errors": error_count, "retry_after": retry_after}
    return _Page(asked=True, error=message)


def _fetched(cursor: WorkspaceSearchCursor, raw_items: list, next_cursor, years) -> _Page:
    # `from_crossref` returns `None` for a non-paper record (D73's Crossref filter); the other four mappers
    # always return a Candidate. `is not None` below is a no-op for those four and the real filter for crossref.
    mapped = [c for raw in raw_items if (c := _MAPPERS[cursor.source](raw)) is not None]
    # ponytail: filtered here, not by each source's own year parameter, so out-of-range pages still count toward
    # the run's iteration cap; pass native year params per source if broad runs hit the cap (D221).
    kept = [c for c in mapped if years is None or years.keeps(c.year)]
    out_of_range = len(mapped) - len(kept)
    cursor.last_error = None
    if next_cursor is None:
        cursor.exhausted = True
    else:
        # A fresh dict with no "errors" key resets the count to 0 (`.get("errors", 0)` in _failed) — a page that
        # succeeds clears whatever error streak came before it.
        cursor.cursor_json = {"value": next_cursor}
    raw = len(raw_items) - out_of_range
    return _Page(True, kept, exhausted=next_cursor is None, raw=raw, out_of_range=out_of_range)


async def _fetch(
    providers: Providers, run: WorkspaceSearchRun, cursor: WorkspaceSearchCursor, years, now: datetime
) -> _Page:
    """One page from the cursor's source. A failure is recorded on the cursor; the run's other sources go on (P7)."""
    source = cursor.source
    client = providers.client(source)
    if client is None:
        return _disabled(cursor)
    # P11: a per-source override (query_overrides_json) takes over that source's query; otherwise the run's
    # own query_text, same as before. Recorded on the run so a later PRISMA export reflects what was actually
    # searched (I6), not just what the caller intended.
    query = run.query_overrides_json.get(source) or run.query_text
    try:
        raw_items, next_cursor = await _PAGE_FUNCS[source](
            client, query, PAGE_SIZE_BY_SOURCE[source], cursor.cursor_json.get("value", 0)
        )
    except httpx.HTTPError as exc:
        return _failed(cursor, exc, now)
    return _fetched(cursor, raw_items, next_cursor, years)


async def search_batch(session: AsyncSession, providers: Providers, run: WorkspaceSearchRun) -> BatchResult:
    """One page per source in `run.sources_json`, merged and deduped, new hits stored. A source that fails (a
    provider's search_page raising httpx.HTTPError, same as discovery.py's existing search()) is recorded in
    `errors` and its cursor gets `last_error`; the run and its other sources are unaffected (spec P7)."""
    query = select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    cursors = {c.source: c for c in (await session.execute(query)).scalars()}
    years = year_range.parse(run.filters_json)
    now = _now()
    pages: dict[str, _Page] = {}
    for source in run.sources_json:
        if _due(cursors.get(source), now):
            pages[source] = await _fetch(providers, run, cursors[source], years, now)
    fetched = {source: page for source, page in pages.items() if page.found is not None}
    stored = await _store_candidates_as_hits(session, run, {source: page.found for source, page in fetched.items()})
    return BatchResult(
        new_hits=stored.new_hits,
        sources_exhausted=[source for source, page in pages.items() if page.exhausted],
        errors={source: page.error for source, page in pages.items() if page.error is not None},
        raw_counts={source: page.raw for source, page in fetched.items()},
        out_of_range={source: page.out_of_range for source, page in fetched.items()},
        new_by_source=stored.new_by_source,
        asked=any(page.asked for page in pages.values()),
    )


async def _pool_hit_id(session: AsyncSession, run: WorkspaceSearchRun, ref: ExternalRef) -> uuid.UUID | None:
    """The workspace's hit for this reference, if the pool has one."""
    return await session.scalar(
        select(WorkspaceSearchHit.id).where(
            WorkspaceSearchHit.workspace_id == run.workspace_id, WorkspaceSearchHit.external_ref_id == ref.id
        )
    )


async def _resolve_hit(
    session: AsyncSession, run: WorkspaceSearchRun, candidate: Candidate, origin: HitOrigin
) -> tuple[uuid.UUID | None, str]:
    """(the hit this candidate is, "existing" | "new" | "raced"). An existing hit, already in the pool (this run or an
    earlier one), keeps its screening decision."""
    ref = await _find_or_create_external_ref(session, candidate)
    existing_id = await _pool_hit_id(session, run, ref)
    if existing_id is not None:
        return existing_id, "existing"
    inserted_id = await _insert_hit(session, run, ref, candidate, origin)
    if inserted_id is None:  # lost a race: the winner's row is the hit
        return await _pool_hit_id(session, run, ref), "raced"
    return inserted_id, "new"


async def _store_candidates_as_hits(
    session: AsyncSession, run: WorkspaceSearchRun, found: dict[str, list[Candidate]], origin: HitOrigin = HitOrigin()
) -> Stored:
    """Merges candidates from every source, dedups against the existing pool by (workspace_id, external_ref_id),
    and stores new ones as hits. Shared by search_batch (source_method="database_search") and snowball
    (source_method="snowball_backward"/"snowball_forward") so both features use exactly one hit-creation/dedup
    path — a paper already in the pool (this run, an earlier one, or a prior snowball hop) keeps its existing
    screening state (spec P8, §9).

    Records one workspace_hit_links row per resolved hit, so a re-found hit gains the new path (kind/parent) too."""
    all_candidates = [c for group in found.values() for c in group]
    merged = merge(found, len(all_candidates)) if all_candidates else []
    new_hits, hit_ids, existing_ids, new_by_source = 0, [], set(), Counter()
    for candidate in merged:
        hit_id, how = await _resolve_hit(session, run, candidate, origin)
        if how == "existing":
            existing_ids.add(hit_id)
        if how == "new":
            new_hits += 1
            new_by_source.update(candidate.sources)
        if hit_id is not None:
            hit_ids.append(hit_id)
    link_ids = hit_ids
    if origin.kind == "search" and run.saved_search_id is not None and existing_ids:
        # a saved search finds the same paper every time it runs: one search link is the whole story
        linked = await hit_links.already_found_by_saved_search(session, run, list(existing_ids))
        link_ids = [c for c in hit_ids if c not in linked]
    await hit_links.record_links(session, run, link_ids, origin.kind, origin.parent_hit_id, origin.parent_paper_id)
    return Stored(new_hits, hit_ids, dict(new_by_source))


async def _insert_hit(
    session: AsyncSession, run: WorkspaceSearchRun, ref: ExternalRef, candidate: Candidate,
    origin: HitOrigin = HitOrigin(),
) -> uuid.UUID | None:
    """Inserts a new pool hit for `ref`, or no-ops if the DB's own `(workspace_id, external_ref_id)` unique
    constraint already has a row for it — not just the caller's own pre-check SELECT, which two workers
    racing the same run (e.g. a stop-then-immediate-restart, since enqueue_job has no dedup job id) can both pass
    before either commits. Returns the new row's id, or None when nothing was inserted (I2)."""
    inserted_id = await session.scalar(
        pg_insert(WorkspaceSearchHit)
        .values(
            workspace_id=run.workspace_id,
            run_id=run.id,
            external_ref_id=ref.id,
            source_method=origin.source_method,
            seed_paper_id=origin.seed_paper_id,
            snowball_round=origin.snowball_round,
            normalized_title=normal_title(candidate.title),
            first_seen_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "external_ref_id"])
        .returning(WorkspaceSearchHit.id)
    )
    return inserted_id
