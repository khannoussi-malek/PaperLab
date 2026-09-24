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
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.candidates import Candidate, from_arxiv, from_core, from_crossref, from_s2, from_work, merge, normal_title
from app.core.discovery import Providers, _add_unpaywall_links, download_pdf
from app.core.references import _same_reference
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import arxiv, core_ac, crossref, openalex, semantic_scholar

if TYPE_CHECKING:
    from app.schemas.workspace_search import HitReviewUpdate

# Provider request page sizes. No source publishes a "max" beyond what its own search_page tests exercise, so
# these mirror discovery.py's PER_SOURCE ballpark, generous enough that most runs exhaust a source in one page.
PAGE_SIZE_BY_SOURCE = {"openalex": 100, "crossref": 30, "arxiv": 20, "core": 20, "semantic_scholar": 75}

# A source stuck on httpx errors (spec §16: unauthenticated S2 search 429s by default) retries this many times
# before its cursor is marked exhausted instead of spinning forever (C2 part 1) — small enough that a real outage
# still lets the run finish on its other sources well inside a job's lifetime.
SOURCE_ERROR_CAP = 3

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
    # Per-source raw item counts for this one batch, pre-merge/pre-dedup — spec §5/§13 wants these for M30b's
    # PRISMA "identified" number, which can't be reconstructed later once a run is exhausted (I1). The worker
    # accumulates these into run.stats_json across iterations; search_batch itself stays stateless.
    raw_counts: dict[str, int] = field(default_factory=dict)


async def _find_or_create_external_ref(session: AsyncSession, candidate: Candidate) -> ExternalRef:
    """The OR-match below can hit more than one row (e.g. one row shares the candidate's DOI, a different row
    shares its s2_id) — `.first()` on an unordered result would pick one arbitrarily, and a wrong pick doesn't
    just risk a bad backfill (handled below), it attaches this hit to the wrong paper outright (Important 2 from
    the fix-round review: a candidate importable later would then download/attach the WRONG row's PDF). DOI is
    the strongest identifier, so when the candidate has one, a DOI-matching row is ordered first — ties among
    several DOI matches (shouldn't happen; doi has no DB-level uniqueness) or candidates with no DOI fall back to
    whatever order the DB happens to return, same as before.

    Backfilling an identifier onto whichever row is picked is only safe when no OTHER row already owns the same
    value: otherwise it either violates external_refs' UNIQUE(s2_id)/UNIQUE(openalex_id) constraint, or — for
    doi/arxiv_id/core_id, which have no DB uniqueness — silently mis-attributes an identifier to the wrong paper
    (spec review I3; this exact mechanism corrupted a real row once, see the ledger's "Closed Access Fixture"
    incident). `pdf_urls` gets its own, stricter check: it only crosses over when the matched row's own DOI
    doesn't contradict the candidate's, so a match found only via a weaker/shared identifier never hands one
    paper's PDF link to a different paper."""
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
    existing = None
    if conditions:
        query = select(ExternalRef).where(or_(*conditions))
        if candidate.doi:
            # `.is_(True)` turns a NULL-doi row's comparison (SQL NULL, not FALSE) into a definite boolean first —
            # otherwise Postgres' NULLS-FIRST-on-DESC default would rank a no-DOI row above an actual DOI match.
            query = query.order_by((ExternalRef.doi == candidate.doi).is_(True).desc())
        existing = (await session.execute(query)).scalars().first()
    if existing is not None:
        for field_name in ("doi", "arxiv_id", "s2_id", "openalex_id", "core_id"):
            value = getattr(candidate, field_name, None)
            if not value or getattr(existing, field_name, None):
                continue  # nothing to backfill, or `existing` already has its own value for this field
            column = getattr(ExternalRef, field_name)
            owned_elsewhere = await session.scalar(
                select(ExternalRef.id).where(column == value, ExternalRef.id != existing.id)
            )
            if owned_elsewhere is None:
                setattr(existing, field_name, value)
        if candidate.pdf_urls and not existing.pdf_urls:
            doi_conflict = existing.doi and candidate.doi and existing.doi != candidate.doi
            if not doi_conflict:
                existing.pdf_urls = candidate.pdf_urls
        if candidate.cited_by_count and not existing.cited_by_count:
            existing.cited_by_count = candidate.cited_by_count
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
    raw_counts: dict[str, int] = {}

    for source in run.sources_json:
        cursor = cursors.get(source)
        if cursor is None or cursor.exhausted:
            continue
        client = providers.client(source)
        if client is None:
            # Disabled/unconfigured (e.g. Unpaywall with no contact_email — the fresh-database default): nothing
            # to fetch here, not an error. Mark it exhausted now so the worker's all(c.exhausted ...) check can
            # still become true once every other source has genuinely exhausted (M30a Task 17 E2E bug).
            cursor.last_error = None
            cursor.exhausted = True
            exhausted.append(source)
            continue
        # P11: a per-source override (query_overrides_json) takes over that source's query; otherwise the run's
        # own query_text, same as before. Recorded on the run so a later PRISMA export reflects what was actually
        # searched (I6), not just what the caller intended.
        query_for_source = run.query_overrides_json.get(source) or run.query_text
        try:
            raw_items, next_cursor = await _PAGE_FUNCS[source](
                client, query_for_source, PAGE_SIZE_BY_SOURCE[source], cursor.cursor_json.get("value", 0)
            )
        except httpx.HTTPError as exc:
            cursor.last_error = str(exc)
            errors[source] = str(exc)
            # Bounded retry (C2 part 1): a source stuck on httpx errors (e.g. an unauthenticated S2 429 — the
            # default case per spec §16's spike, not an edge case) must eventually stop retrying instead of
            # spinning until the worker's job_timeout kills it mid-commit.
            error_count = cursor.cursor_json.get("errors", 0) + 1
            cursor.cursor_json = {**cursor.cursor_json, "errors": error_count}
            if error_count >= SOURCE_ERROR_CAP:
                cursor.exhausted = True
                exhausted.append(source)
            continue
        found[source] = [c for raw in raw_items if (c := _MAPPERS[source](raw)) is not None]
        raw_counts[source] = len(raw_items)
        cursor.last_error = None
        if next_cursor is None:
            cursor.exhausted = True
            exhausted.append(source)
        else:
            # A fresh dict with no "errors" key resets the count to 0 (`.get("errors", 0)` above) — a page that
            # succeeds clears whatever error streak came before it.
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
        if await _insert_hit(session, run, ref, candidate):
            new_hits += 1

    return BatchResult(new_hits=new_hits, sources_exhausted=exhausted, errors=errors, raw_counts=raw_counts)


async def _insert_hit(
    session: AsyncSession, run: WorkspaceSearchRun, ref: ExternalRef, candidate: Candidate
) -> bool:
    """Inserts a new pool hit for `ref`, or no-ops if the DB's own `(workspace_id, external_ref_id)` unique
    constraint already has a row for it — not just this function's own pre-check SELECT above, which two workers
    racing the same run (e.g. a stop-then-immediate-restart, since enqueue_job has no dedup job id) can both pass
    before either commits. Returns whether a row was actually inserted (I2)."""
    inserted_id = await session.scalar(
        pg_insert(WorkspaceSearchHit)
        .values(
            workspace_id=run.workspace_id,
            run_id=run.id,
            external_ref_id=ref.id,
            source_method="database_search",
            normalized_title=normal_title(candidate.title),
            first_seen_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "external_ref_id"])
        .returning(WorkspaceSearchHit.id)
    )
    return inserted_id is not None


from app.core import paper_sources, papers, workspaces
from app.core.errors import Conflict, InvalidInput, NotFound

# OpenAlex's `page` cursor is 1-based; every other source's is a 0-based offset (Task 2's convention — the
# engine tests' own START_CURSOR already knows this). Seeding OpenAlex at 0 asked its fake for a negative offset
# and got nothing back "by coincidence," hiding the bug (I4).
_STARTING_CURSOR_VALUE = {"openalex": 1}


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

    if filters:
        # Real per-source filter translation is out of scope for this fix wave — recording a filter the run never
        # actually applied would misreport the search strategy a PRISMA methods section later cites (I6 part 2).
        raise InvalidInput("search run filters are not supported yet")

    # D73's merge trust order (app/core/paper_sources.SOURCES) is what search_batch's `found` dict — insertion
    # ordered, fed straight into merge()'s ranking — relies on; storing sources in whatever order the caller sent
    # them silently let the caller's field order become the trust order instead.
    ordered_sources = [source for source in paper_sources.SOURCES if source in sources]

    run = WorkspaceSearchRun(
        workspace_id=workspace_id, query_text=query_text, filters_json=filters,
        query_overrides_json=query_overrides or {}, sources_json=ordered_sources, status="running",
        started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    for source in ordered_sources:
        seed = {"value": _STARTING_CURSOR_VALUE.get(source, 0)}
        session.add(WorkspaceSearchCursor(run_id=run.id, source=source, cursor_json=seed))
    await session.commit()
    return run


async def stop_run(session: AsyncSession, run_id, workspace_id=None) -> WorkspaceSearchRun:
    run = await get_run(session, run_id, workspace_id)
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


def _encode_cursor(first_seen_at: datetime, hit_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([first_seen_at.isoformat(), str(hit_id)]).encode()).decode()


_HIT_COLUMNS = [column.name for column in WorkspaceSearchHit.__table__.columns]


def _hit_out_dict(hit: WorkspaceSearchHit, ref: ExternalRef | None) -> dict:
    """A hit's own columns plus its linked ExternalRef's title/authors/year/venue/doi, merged into one dict for
    HitOut (I7). This codebase's models never use relationship() (a manual join/lookup is the convention), so the
    caller passes in whichever `ref` it already has — a join row here, an explicit session.get elsewhere — and
    this just does the merge, once, the same way for all three HitOut-producing call sites below."""
    data = {name: getattr(hit, name) for name in _HIT_COLUMNS}
    data.update(
        title=ref.title if ref else None,
        authors=ref.authors if ref else None,
        year=ref.year if ref else None,
        venue=ref.venue if ref else None,
        doi=ref.doi if ref else None,
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
    stage1_status: str | None = None, acquisition_status: str | None = None,
) -> tuple[list[dict], str | None]:
    """Keyset-paginated hit listing, ordered by (first_seen_at, id) so the cursor is stable even when several
    hits share a first_seen_at timestamp. `tuple_()` on both sides makes SQLAlchemy emit a real SQL row-value
    comparison (`WHERE (first_seen_at, id) > (:seen_at, :id)`) instead of a no-op Python tuple comparison.

    Outer-joins ExternalRef (I7) since external_ref_id is nullable — a hit with no linked ref still comes back,
    with title/authors/year/venue/doi all None via `_hit_out_dict`."""
    query = (
        select(WorkspaceSearchHit, ExternalRef)
        .join(ExternalRef, WorkspaceSearchHit.external_ref_id == ExternalRef.id, isouter=True)
        .where(WorkspaceSearchHit.workspace_id == workspace_id)
    )
    if stage1_status:
        query = query.where(WorkspaceSearchHit.stage1_status == stage1_status)
    if acquisition_status:
        query = query.where(WorkspaceSearchHit.acquisition_status == acquisition_status)
    if after:
        seen_at, hit_id = _decode_cursor(after)
        query = query.where(
            tuple_(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id) > tuple_(seen_at, hit_id)
        )
    query = query.order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id).limit(limit)
    rows = (await session.execute(query)).all()
    items = [_hit_out_dict(hit, ref) for hit, ref in rows]
    next_cursor = _encode_cursor(rows[-1][0].first_seen_at, rows[-1][0].id) if len(rows) == limit else None
    return items, next_cursor


async def review_hit(session: AsyncSession, hit_id, workspace_id, update: "HitReviewUpdate") -> dict:
    """Stage-1 screening update for one hit. Scoped to workspace_id (same ownership rule as get_run/stop_run) so a
    hit_id guessed or leaked from another workspace can't be patched through this route."""
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
    result = await session.execute(
        select(WorkspaceSearchHit).where(
            WorkspaceSearchHit.id.in_(hit_ids), WorkspaceSearchHit.workspace_id == workspace_id
        )
    )
    hits = result.scalars().all()
    for hit in hits:
        hit.stage1_status = stage1_status
        if stage1_exclude_reason:
            hit.stage1_exclude_reason = stage1_exclude_reason
        if priority is not None:
            hit.priority = priority
    await session.commit()
    return len(hits)


@dataclass(frozen=True)
class ImportResult:
    imported: int
    failed: int
    paper_ids: list[uuid.UUID] = field(default_factory=list)


async def import_hits(
    session: AsyncSession, providers: Providers, workspace_id: uuid.UUID, hit_ids: list[uuid.UUID] | None
) -> ImportResult:
    """Best-effort bulk import (spec Task 9), mirroring discovery.add's one-candidate download-then-create flow:
    every targeted hit (hit_ids, or every not-yet-imported `relevant` hit) gets its own outcome, so one hit with no
    free PDF never stops the rest of the batch. A hit left `failed` is Manual acquisition's job (Task 11).
    `paper_ids` are the newly created papers, for the route to enqueue ingest on — a core function has no
    Request to enqueue with itself. A hit whose ExternalRef.imported_as is already set (import_reference's own
    bookkeeping, same as ours below) is attached to that existing paper without downloading again, and its
    paper_id is left out of paper_ids so ingest isn't re-enqueued for a paper that already went through it."""
    query = select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace_id)
    query = (
        query.where(WorkspaceSearchHit.id.in_(hit_ids))
        if hit_ids
        else query.where(WorkspaceSearchHit.stage1_status == "relevant")
    )
    hits = (await session.execute(query)).scalars().all()

    imported, failed, paper_ids = 0, 0, []
    for hit in hits:
        if hit.acquisition_status in ("imported", "manual"):
            # "manual" is its own provenance (spec §4.4/M30b's PRISMA export need it distinguished from an
            # automatic import) — re-running Import all must never quietly relabel it "imported" (I8).
            continue
        ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
        if ref is not None and ref.imported_as is not None:
            # Already in the library — an earlier hit in this batch, an earlier run, or the References panel.
            # Attach the existing paper instead of downloading/creating a duplicate, and don't re-enqueue ingest.
            await workspaces.add_paper(session, workspace_id, ref.imported_as)
            hit.acquisition_status = "imported"
            hit.paper_id = ref.imported_as
            imported += 1
            continue
        if ref is not None and not ref.pdf_urls and ref.doi:
            # Unpaywall's real role (spec §6): DOI-only PDF enrichment for a candidate missing one, applied
            # post-merge — never a discovery source. import_hits only ever looked at pdf_urls as already stored;
            # try this once before giving up (I5). providers.unpaywall may be None (source off) — the helper
            # already treats that as a no-op, same as discovery.add()'s own callers do.
            [enriched] = await _add_unpaywall_links(
                providers.unpaywall, [Candidate(title=ref.title, doi=ref.doi, arxiv_id=ref.arxiv_id)]
            )
            if enriched.pdf_urls:
                ref.pdf_urls = enriched.pdf_urls
        data = await download_pdf(providers.pdf, ref.pdf_urls) if ref and ref.pdf_urls else None
        if data is None:
            hit.acquisition_status = "failed"
            failed += 1
            continue
        paper = await papers.create_paper(
            session, f"{hit.normalized_title}.pdf", data, settings.pdf_dir, prefill={"title": ref.title}
        )
        await workspaces.add_paper(session, workspace_id, paper.id)
        same_paper = [ExternalRef.id == ref.id, *_same_reference(ref.s2_id, ref.openalex_id, ref.doi, ref.arxiv_id)]
        await session.execute(update(ExternalRef).where(or_(*same_paper)).values(imported_as=paper.id))
        hit.acquisition_status = "imported"
        hit.paper_id = paper.id
        imported += 1
        paper_ids.append(paper.id)

    await session.commit()
    return ImportResult(imported, failed, paper_ids)


async def upload_hit_pdf(
    session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID, filename: str | None, content: bytes
) -> tuple[dict, bool]:
    """Manual acquisition (spec Task 10) for a hit with no free PDF: the user supplies the file directly instead of
    `import_hits` finding one. Same ownership scoping and already-imported handling as `import_hits` above — a
    hit whose ExternalRef.imported_as is already set gets the existing paper attached, no new paper, no re-enqueue.
    Returns (hit, created) so the route only enqueues ingest when this call actually created a new paper.

    The %PDF-body check is the trust boundary for this user-uploaded file (spec's Global Constraint): reject
    before touching the already-imported branch too, using the same magic bytes `papers.create_paper` checks."""
    if not content.startswith(papers.PDF_MAGIC):
        raise InvalidInput("uploaded file is not a PDF")

    hit = await session.get(WorkspaceSearchHit, hit_id)
    if hit is None or hit.workspace_id != workspace_id:
        raise NotFound(f"hit {hit_id} not found")

    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    if ref is not None and ref.imported_as is not None:
        await workspaces.add_paper(session, workspace_id, ref.imported_as)
        hit.acquisition_status = "manual"
        hit.paper_id = ref.imported_as
        await session.commit()
        return _hit_out_dict(hit, ref), False

    paper = await papers.create_paper(
        session, filename or f"{hit.normalized_title}.pdf", content, settings.pdf_dir,
        prefill={"title": ref.title} if ref else None,
    )
    await workspaces.add_paper(session, workspace_id, paper.id)
    if ref is not None:
        same_paper = [ExternalRef.id == ref.id, *_same_reference(ref.s2_id, ref.openalex_id, ref.doi, ref.arxiv_id)]
        await session.execute(update(ExternalRef).where(or_(*same_paper)).values(imported_as=paper.id))
    hit.acquisition_status = "manual"
    hit.paper_id = paper.id
    await session.commit()
    return _hit_out_dict(hit, ref), True
