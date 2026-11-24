"""One fetch pass of a search run: ask each source for its next page, store new candidates as hits, back off a failing source."""

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


async def _find_or_create_external_ref(
    session: AsyncSession, candidate: Candidate, *, backfill: bool = True
) -> ExternalRef:
    """The OR-match below can hit more than one row (e.g. one row shares the candidate's DOI, a different row
    shares its semantic_scholar id) — `.first()` on an unordered result would pick one arbitrarily, and a wrong
    pick doesn't just risk a bad backfill (handled below), it attaches this hit to the wrong paper outright
    (Important 2 from the fix-round review: a candidate importable later would then download/attach the WRONG
    row's PDF). DOI is the strongest identifier, so when the candidate has one, a DOI-matching row is ordered
    first — ties among several DOI matches (shouldn't happen; doi has no DB-level uniqueness) or candidates with
    no DOI fall back to whatever order the DB happens to return, same as before.

    Backfilling an identifier onto whichever row is picked is only safe when no OTHER row already owns the same
    value: otherwise it either violates the partial unique indexes on external_ids->>'openalex'/'semantic_scholar'
    (Phase 0b), or — for doi/arxiv/core, which have no DB uniqueness — silently mis-attributes an identifier to
    the wrong paper (spec review I3; this exact mechanism corrupted a real row once, see the ledger's "Closed
    Access Fixture" incident). `pdf_urls` gets its own, stricter check: it only crosses over when the matched
    row's own DOI doesn't contradict the candidate's, so a match found only via a weaker/shared identifier never
    hands one paper's PDF link to a different paper."""
    conditions = [
        ExternalRef.external_ids[source].astext == value for source, value in candidate.external_ids.items()
    ]
    if candidate.doi:
        conditions.append(ExternalRef.doi == candidate.doi)
    existing = None
    if conditions:
        query = select(ExternalRef).where(or_(*conditions))
        if candidate.doi:
            # `.is_(True)` turns a NULL-doi row's comparison (SQL NULL, not FALSE) into a definite boolean first —
            # otherwise Postgres' NULLS-FIRST-on-DESC default would rank a no-DOI row above an actual DOI match.
            query = query.order_by((ExternalRef.doi == candidate.doi).is_(True).desc())
        existing = (await session.execute(query)).scalars().first()
    if existing is not None:
        if not backfill:  # a package import only reads a library reference; it never edits one (M35c M1)
            return existing
        external_ids = dict(existing.external_ids)
        for source, value in candidate.external_ids.items():
            if source in external_ids:
                continue  # `existing` already has its own value for this source
            owned_elsewhere = await session.scalar(
                select(ExternalRef.id).where(
                    ExternalRef.external_ids[source].astext == value, ExternalRef.id != existing.id
                )
            )
            if owned_elsewhere is None:
                external_ids[source] = value
        if external_ids != existing.external_ids:
            existing.external_ids = external_ids
        if candidate.doi and not existing.doi:
            owned_elsewhere = await session.scalar(
                select(ExternalRef.id).where(ExternalRef.doi == candidate.doi, ExternalRef.id != existing.id)
            )
            if owned_elsewhere is None:
                existing.doi = candidate.doi
        if candidate.pdf_urls and not existing.pdf_urls:
            doi_conflict = existing.doi and candidate.doi and existing.doi != candidate.doi
            if not doi_conflict:
                existing.pdf_urls = candidate.pdf_urls
        if candidate.cited_by_count and not existing.cited_by_count:
            existing.cited_by_count = candidate.cited_by_count
        if candidate.abstract and not existing.abstract:
            existing.abstract = candidate.abstract
        for triage in ("source_type", "published_doi", "published_venue"):
            if getattr(candidate, triage) and not getattr(existing, triage):
                setattr(existing, triage, getattr(candidate, triage))
        # Union, not backfill-if-empty like the fields above: a later search or snowball round can rediscover an
        # already-known paper through a source that hadn't found it before, and every one of those is worth
        # keeping, not just whichever happened to create the row.
        if candidate.sources:
            existing.sources = list(dict.fromkeys([*existing.sources, *candidate.sources]))
        return existing
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


def _now() -> datetime:
    """A thin wrapper around datetime.now(timezone.utc), so a test can monkeypatch just this module's own clock
    reads for the error-backoff check below without needing a real sleep — same reasoning as
    workers/workspace_search.py's own _now() wrapper (that one for a wall-clock deadline, this one for a
    per-source retry cooldown)."""
    return datetime.now(timezone.utc)


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
    raw_counts: dict[str, int] = {}
    years = year_range.parse(run.filters_json)
    out_of_range: dict[str, int] = {}

    now = _now()
    asked = False
    for source in run.sources_json:
        cursor = cursors.get(source)
        if cursor is None or cursor.exhausted or cursor.cursor_json.get("paused"):
            continue
        retry_after = cursor.cursor_json.get("retry_after")
        if retry_after and now < datetime.fromisoformat(retry_after):
            continue  # cooling down from a recent error — not a failure, not exhausted, just not due yet
        client = providers.client(source)
        if client is None:
            # Disabled/unconfigured (e.g. Unpaywall with no contact_email — the fresh-database default): nothing
            # to fetch here, not an error. Mark it exhausted now so the worker's all(c.exhausted ...) check can
            # still become true once every other source has genuinely exhausted (M30a Task 17 E2E bug).
            cursor.last_error = None
            cursor.exhausted = True
            cursor.cursor_json = {**cursor.cursor_json, "disabled": True}
            exhausted.append(source)
            continue
        asked = True
        # P11: a per-source override (query_overrides_json) takes over that source's query; otherwise the run's
        # own query_text, same as before. Recorded on the run so a later PRISMA export reflects what was actually
        # searched (I6), not just what the caller intended.
        query_for_source = run.query_overrides_json.get(source) or run.query_text
        try:
            raw_items, next_cursor = await _PAGE_FUNCS[source](
                client, query_for_source, PAGE_SIZE_BY_SOURCE[source], cursor.cursor_json.get("value", 0)
            )
        except httpx.HTTPError as exc:
            message = str(exc) or type(exc).__name__  # a timeout's own text is empty
            cursor.last_error = message
            errors[source] = message
            # Bounded retry (C2 part 1): a source stuck on httpx errors (e.g. an unauthenticated S2 429 — the
            # default case per spec §16's spike, not an edge case) must eventually stop retrying instead of
            # spinning until the worker's job_timeout kills it mid-commit. Spaced out (see SOURCE_ERROR_CAP's
            # comment), not consecutive, so a brief/transient error gets a real chance to clear before the source
            # is abandoned for the rest of the run.
            error_count = cursor.cursor_json.get("errors", 0) + 1
            if error_count >= SOURCE_ERROR_CAP:
                cursor.exhausted = True
                exhausted.append(source)
                cursor.cursor_json = {**cursor.cursor_json, "errors": error_count}
            else:
                backoff = _ERROR_BACKOFF_SECONDS[min(error_count - 1, len(_ERROR_BACKOFF_SECONDS) - 1)]
                cursor.cursor_json = {
                    **cursor.cursor_json,
                    "errors": error_count,
                    "retry_after": (now + timedelta(seconds=backoff)).isoformat(),
                }
            continue
        # `from_crossref` returns `None` for a non-paper record (D73's Crossref filter); the other four mappers
        # always return a Candidate. `is not None` below is a no-op for those four and the real filter for crossref.
        mapped = [c for raw in raw_items if (c := _MAPPERS[source](raw)) is not None]
        # ponytail: filtered here, not by each source's own year parameter, so out-of-range pages still count toward
        # the run's iteration cap; pass native year params per source if broad runs hit the cap (D221).
        found[source] = [c for c in mapped if years is None or years.keeps(c.year)]
        out_of_range[source] = len(mapped) - len(found[source])
        raw_counts[source] = len(raw_items) - out_of_range[source]
        cursor.last_error = None
        if next_cursor is None:
            cursor.exhausted = True
            exhausted.append(source)
        else:
            # A fresh dict with no "errors" key resets the count to 0 (`.get("errors", 0)` above) — a page that
            # succeeds clears whatever error streak came before it.
            cursor.cursor_json = {"value": next_cursor}

    new_by_source: Counter[str] = Counter()
    new_hits, _ = await _store_candidates_as_hits(
        session, run, "database_search", found, new_by_source=new_by_source
    )

    return BatchResult(new_hits=new_hits, sources_exhausted=exhausted, errors=errors, raw_counts=raw_counts,
                       out_of_range=out_of_range, new_by_source=dict(new_by_source), asked=asked)


async def _store_candidates_as_hits(
    session: AsyncSession, run: WorkspaceSearchRun, source_method: str, found: dict[str, list[Candidate]],
    seed_paper_id: uuid.UUID | None = None, snowball_round: int | None = None,
    new_by_source: Counter[str] | None = None, kind: str = "search",
    parent_hit_id: uuid.UUID | None = None, parent_paper_id: uuid.UUID | None = None,
) -> tuple[int, list[uuid.UUID]]:
    """Merges candidates from every source, dedups against the existing pool by (workspace_id, external_ref_id),
    and stores new ones as hits. Shared by search_batch (source_method="database_search") and snowball
    (source_method="snowball_backward"/"snowball_forward") so both features use exactly one hit-creation/dedup
    path — a paper already in the pool (this run, an earlier one, or a prior snowball hop) keeps its existing
    screening state (spec P8, §9).

    Returns (new hit count, ids of every hit these candidates resolved to, new and existing) and records one
    workspace_hit_links row per resolved hit, so a re-found hit gains the new path (kind/parent) too."""
    all_candidates = [c for group in found.values() for c in group]
    merged = merge(found, len(all_candidates)) if all_candidates else []

    new_hits = 0
    child_ids: list[uuid.UUID] = []
    existing_ids: set[uuid.UUID] = set()
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
            # already in the pool (this run or an earlier one) — keeps its existing screening decision
            child_ids.append(existing_hit.id)
            existing_ids.add(existing_hit.id)
            continue
        inserted_id = await _insert_hit(
            session, run, ref, candidate, source_method=source_method,
            seed_paper_id=seed_paper_id, snowball_round=snowball_round,
        )
        if inserted_id is None:  # lost a race: the winner's row is the hit
            inserted_id = await session.scalar(
                select(WorkspaceSearchHit.id).where(
                    WorkspaceSearchHit.workspace_id == run.workspace_id,
                    WorkspaceSearchHit.external_ref_id == ref.id,
                )
            )
        else:
            new_hits += 1
            if new_by_source is not None:
                new_by_source.update(candidate.sources)
        if inserted_id is not None:
            child_ids.append(inserted_id)
    link_ids = child_ids
    if kind == "search" and run.saved_search_id is not None and existing_ids:
        # a saved search finds the same paper every time it runs: one search link is the whole story
        linked = await hit_links.already_found_by_saved_search(session, run, list(existing_ids))
        link_ids = [c for c in child_ids if c not in linked]
    await hit_links.record_links(session, run, link_ids, kind, parent_hit_id, parent_paper_id)
    return new_hits, child_ids


async def _insert_hit(
    session: AsyncSession, run: WorkspaceSearchRun, ref: ExternalRef, candidate: Candidate,
    source_method: str = "database_search", seed_paper_id: uuid.UUID | None = None,
    snowball_round: int | None = None,
) -> uuid.UUID | None:
    """Inserts a new pool hit for `ref`, or no-ops if the DB's own `(workspace_id, external_ref_id)` unique
    constraint already has a row for it — not just this function's own pre-check SELECT above, which two workers
    racing the same run (e.g. a stop-then-immediate-restart, since enqueue_job has no dedup job id) can both pass
    before either commits. Returns the new row's id, or None when nothing was inserted (I2)."""
    inserted_id = await session.scalar(
        pg_insert(WorkspaceSearchHit)
        .values(
            workspace_id=run.workspace_id,
            run_id=run.id,
            external_ref_id=ref.id,
            source_method=source_method,
            seed_paper_id=seed_paper_id,
            snowball_round=snowball_round,
            normalized_title=normal_title(candidate.title),
            first_seen_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "external_ref_id"])
        .returning(WorkspaceSearchHit.id)
    )
    return inserted_id
