"""The MCP tools for systematic search: runs, hits, screening and AI pre-screening, snowballing, eligibility, PRISMA."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers import paper_enrichment, paper_sources
from app.core.papers.pipeline import _refuse_remote, workspace_id
from app.core.platform import queue
from app.core.search import (
    hit_enrichment,
    hit_import,
    hit_ranking,
    prisma_export,
    screening,
    search_hits,
    snowball_run,
    source_clients,
    workspace_search,
)
from app.core.search.source_registry import DISCOVERY_SOURCE_IDS
from app.core.workspaces import tags, workspaces
from app.domain.errors import Conflict, InvalidInput, NotFound
from app.schemas.workspace_search import HitOut, ScreeningStateOut, SearchRunOut, SearchRunSummary


async def _sources(session: AsyncSession, sources: list[str] | None) -> list[str]:
    if sources:
        unknown = [s for s in sources if s not in DISCOVERY_SOURCE_IDS]
        if unknown:
            raise InvalidInput("unknown_source", unknown=unknown, valid=list(DISCOVERY_SOURCE_IDS))
        return sources
    on = (await paper_sources.get(session)).enabled
    chosen = [s for s in DISCOVERY_SOURCE_IDS if on.get(s)]
    if not chosen:
        raise InvalidInput("No paper source is on. Turn one on in Settings → Paper sources, or name `sources`.")
    return chosen


async def start_search_run(
    session: AsyncSession, workspace: str, query: str, sources: list[str] | None = None,
    year_from: int | None = None, year_to: int | None = None,
) -> SearchRunOut:
    ws = await workspace_id(session, workspace)
    if not query.strip():
        raise InvalidInput("Give the search a query.")
    filters = {"year_from": year_from, "year_to": year_to}
    run = await workspace_search.start_run(session, ws, query.strip(), filters, await _sources(session, sources))
    await queue.enqueue("run_workspace_search", str(run.id))
    return await workspace_search.run_out(session, run)


async def get_search_run(session: AsyncSession, run_id: uuid.UUID) -> SearchRunOut:
    return await workspace_search.run_out(session, await workspace_search.get_run(session, run_id))


async def list_search_runs(session: AsyncSession, workspace: str, limit: int = 20) -> list[SearchRunSummary]:
    runs = await workspace_search.list_runs(
        session, await workspace_id(session, workspace), max(1, min(limit, MAX_HITS))
    )
    return await workspace_search.run_summaries(session, runs)


async def stop_search_run(session: AsyncSession, run_id: uuid.UUID) -> SearchRunOut:
    return await workspace_search.run_out(session, await workspace_search.stop_run(session, run_id))


async def continue_search_run(session: AsyncSession, run_id: uuid.UUID) -> SearchRunOut:
    run = await workspace_search.get_run(session, run_id)
    run = await workspace_search.continue_run(session, run.workspace_id, run.id)
    await queue.enqueue("run_workspace_search", str(run.id))
    return await workspace_search.run_out(session, run)


DECISIONS = ("relevant", "not_relevant", "maybe")
REASONS = ("wrong_topic", "wrong_study_type", "duplicate", "language", "inaccessible", "other")
MAX_HITS = 100


@dataclass(frozen=True)
class HitPage:
    hits: list[HitOut]
    next_cursor: str | None


@dataclass(frozen=True)
class ReviewResult:
    updated: int
    skipped: list[uuid.UUID]


async def list_hits(
    session: AsyncSession, workspace: str, run_id: uuid.UUID | None = None, status: str | None = None,
    cursor: str | None = None, limit: int = 50,
) -> HitPage:
    if status is not None and status not in (*DECISIONS, "undecided"):
        raise InvalidInput("invalid_decision", valid=[*DECISIONS, "undecided"])
    ws = await workspace_id(session, workspace)
    items, next_cursor = await search_hits.list_hits(
        session, ws, limit=max(1, min(limit, MAX_HITS)), after=cursor, stage1_status=status, run_id=run_id
    )
    return HitPage(hits=[HitOut.model_validate(item) for item in items], next_cursor=next_cursor)


async def get_screening_suggestions(
    session: AsyncSession, workspace: str, run_id: uuid.UUID | None = None, min_relevance: int | None = None,
    cursor: str | None = None, limit: int = 50,
) -> HitPage:
    """Undecided hits the model has a suggestion for, best score first."""
    ws = await workspace_id(session, workspace)
    items, next_cursor = await search_hits.list_hits(
        session, ws, limit=max(1, min(limit, MAX_HITS)), after=cursor, stage1_status="undecided", run_id=run_id,
        sort="ai", min_relevance=min_relevance, suggested_only=True,
    )
    return HitPage(hits=[HitOut.model_validate(item) for item in items], next_cursor=next_cursor)


async def get_screening_criteria(session: AsyncSession, workspace: str) -> ScreeningStateOut:
    """The workspace's research question, inclusion and exclusion criteria (and the pre-screening state)."""
    return ScreeningStateOut.model_validate(await screening.get_state(session, await workspace_id(session, workspace)))


async def set_screening_criteria(
    session: AsyncSession, workspace: str, research_question: str | None = None,
    inclusion_criteria: str | None = None, exclusion_criteria: str | None = None,
) -> ScreeningStateOut:
    """Saves only the fields given (an empty string clears one), as the screening page does. A real change clears
    every stored AI suggestion. Refused while suggestions are being made: stop them first."""
    ws = await workspace_id(session, workspace)
    if (await screening.get_state(session, ws))["suggest_status"] != "idle":
        raise Conflict("suggestions_running", detail="Stop the AI suggestions before changing the criteria.")
    given = {key: value for key, value in (("research_question", research_question), ("inclusion", inclusion_criteria),
                                           ("exclusion", exclusion_criteria)) if value is not None}
    state = await screening.set_criteria(session, ws, **given) if given else await screening.get_state(session, ws)
    return ScreeningStateOut.model_validate(state)


PRESCREEN_CONFIRM_ABOVE = 500  # a workspace-wide run once queued 13,720 hits and ran for 4 hours


async def run_prescreen(
    session: AsyncSession, workspace: str, run_id: uuid.UUID | None = None, confirm: bool = False,
    allow_remote: bool = False, run_ids: list[uuid.UUID] | None = None,
) -> ScreeningStateOut:
    """Starts AI pre-screening. There is no confirm dialog over MCP, so a remote default model is refused unless
    allow_remote is set (the owner agreed), and so is a workspace-wide queue over PRESCREEN_CONFIRM_ABOVE hits
    unless confirm is set. The two are independent. run_ids queues several runs as one job."""
    if run_id is not None and run_ids is not None:
        raise InvalidInput("run_id_or_run_ids")
    if run_ids is not None and not run_ids:
        raise InvalidInput("run_ids_empty")
    ws = await workspace_id(session, workspace)
    run_ids = None if run_ids is None else list(dict.fromkeys(run_ids))
    for each in [run_id] if run_id is not None else run_ids or []:
        await workspace_search.get_run(session, each, workspace_id=ws)  # NotFound for a foreign run
    await _refuse_remote(session, allow_remote)
    if run_id is None and not confirm:
        # ponytail: loads the pool twice on a workspace-wide call (here and in start_suggestions); pass the count
        # through if it shows up in timings.
        queued = len(screening.suggestion_queue(await hit_ranking.load_pool(session, ws), run_ids=run_ids))
        if queued > PRESCREEN_CONFIRM_ABOVE:
            raise Conflict("prescreen_needs_confirm", queued=queued, limit=PRESCREEN_CONFIRM_ABOVE)
    state = await screening.start_suggestions(session, ws, allow_remote, run_id, run_ids=run_ids)
    if run_ids is None:
        await queue.enqueue("suggest_screening", str(ws))
    else:
        await queue.enqueue("suggest_screening", str(ws), [str(r) for r in run_ids])
    return ScreeningStateOut.model_validate(state)


@dataclass(frozen=True)
class RecheckQueued:
    queued: int
    already_running: bool = False
    left: int = 0  # past the cap: call again once this batch has run


MAX_RECHECK_PAPERS = 200  # about 20 minutes at a look every few seconds


async def recheck_free_copies(
    session: AsyncSession, workspace: str, tags_: list[str] | None = None, match: Literal["any", "all"] = "any"
) -> RecheckQueued:
    """Queues a fresh look for a free copy of a workspace's papers with no PDF (optionally those with these tags). The
    job runs in the background; each paper's pdf_check_result then says what it found."""
    ws = await workspace_id(session, workspace)
    wanted = await tags.paper_ids(session, ws, tags_, match)
    missing = [
        str(row.id) for row in await workspaces.papers(session, ws)
        if not row.has_pdf and (wanted is None or row.id in wanted)
    ]
    if not missing:
        return RecheckQueued(0)
    batch = missing[:MAX_RECHECK_PAPERS]
    started = await queue.enqueue("recheck_papers", batch, job_id=f"recheck_papers:{ws}")  # one per workspace at a time
    if not started:
        return RecheckQueued(0, already_running=True, left=len(missing))
    return RecheckQueued(len(batch), left=len(missing) - len(batch))


@dataclass(frozen=True)
class EnrichQueued:
    queued: int
    already_running: bool = False
    suggestions_cleared: int = 0
    s2_off: bool = False  # Semantic Scholar is off in Settings: nothing was queued


async def enrich_hits(session: AsyncSession, workspace: str, run_id: uuid.UUID | None = None) -> EnrichQueued:
    """Queues the Semantic Scholar backfill for hits not asked about yet. `queued` is how many; calling again shows
    what a rate-limited run left, and `already_running` means a job for it is still going, so nothing new started.
    A hit Semantic Scholar couldn't fill is asked once only; arXiv gaps are asked
    again. With Semantic Scholar turned off in Settings nothing is queued (`s2_off`). Hits whose 'no abstract'
    suggestion is now out of date are cleared (`suggestions_cleared`), so run_prescreen picks them up again."""
    ws = await workspace_id(session, workspace)
    await workspaces.require_writable(session, ws)
    if run_id is not None:
        await workspace_search.get_run(session, run_id, workspace_id=ws)  # NotFound for a foreign run
    cleared = await hit_enrichment.clear_stale_no_abstract(session, ws)  # needs no Semantic Scholar
    if not (await paper_sources.get(session)).enabled["semantic_scholar"]:
        return EnrichQueued(0, suggestions_cleared=cleared, s2_off=True)
    s2_refs = await hit_enrichment.refs_to_enrich(session, ws, run_id)
    count = len({r.id for r in [*s2_refs, *await hit_enrichment.refs_for_arxiv(session, ws, run_id)]})
    if not count:
        return EnrichQueued(0, suggestions_cleared=cleared)
    # One job per workspace and run at a time: arq refuses a duplicate id while one is queued or running.
    started = await queue.enqueue(
        "enrich_hits", str(ws), str(run_id) if run_id else None, job_id=f"enrich_hits:{ws}:{run_id or 'all'}"
    )
    return EnrichQueued(count, already_running=not started, suggestions_cleared=cleared)


@dataclass(frozen=True)
class EnrichPapersQueued:
    queued: int
    already_running: bool = False
    s2_off: bool = False  # Semantic Scholar is off in Settings: nothing was queued


async def enrich_papers(session: AsyncSession, workspace: str) -> EnrichPapersQueued:
    """Queues the Semantic Scholar lookup of the workspace's papers' published versions. `queued` is how many papers
    have not been asked about yet; calling again shows what a rate-limited run left, and `already_running` means a
    job for it is still going, so nothing new started. With Semantic Scholar off in Settings nothing is queued."""
    ws = await workspace_id(session, workspace)
    if not (await paper_sources.get(session)).enabled["semantic_scholar"]:
        return EnrichPapersQueued(0, s2_off=True)
    count = len(await paper_enrichment.papers_to_enrich(session, ws))
    if not count:
        return EnrichPapersQueued(0)
    started = await queue.enqueue("enrich_papers", str(ws), job_id=f"enrich_papers:{ws}")
    return EnrichPapersQueued(count, already_running=not started)


async def stop_prescreen(session: AsyncSession, workspace: str) -> ScreeningStateOut:
    """Stops pre-screening; idle when nothing runs, and a second call on a stuck 'stopping' resets it."""
    state = await screening.stop_suggestions(session, await workspace_id(session, workspace))
    return ScreeningStateOut.model_validate(state)


MAX_ACCEPT_HITS = 5000  # the API's cap


async def accept_suggestions(
    session: AsyncSession, workspace: str, hit_ids: list[uuid.UUID], tags_: list[str] | None = None
) -> screening.AcceptResult:
    """Records the owner's decision from each suggestion: include becomes relevant, exclude not_relevant. `tags_`
    go on the accepted hits only."""
    if len(hit_ids) > MAX_ACCEPT_HITS:
        raise InvalidInput("too_many_hits", max=MAX_ACCEPT_HITS)
    for name in tags_ or ():
        tags.normalize(name)  # refuse a bad name before any decision is written
    ws = await workspace_id(session, workspace)
    accepted = await screening.accept_suggestions(session, ws, hit_ids)
    if tags_:
        skipped = set(accepted.skipped)
        await tags.tag_hits(session, ws, tags_, [h for h in hit_ids if h not in skipped])
    return accepted


async def review_hits(
    session: AsyncSession, workspace: str, hit_ids: list[uuid.UUID], decision: str, reason: str | None = None,
    tags_: list[str] | None = None,
) -> ReviewResult:
    """Records the owner's stage-1 decision (Claude Code asks before each call). Hits outside the workspace are
    skipped, never written (D218)."""
    if decision not in DECISIONS or (reason is not None and reason not in REASONS):
        raise InvalidInput("invalid_decision", decisions=list(DECISIONS), reasons=list(REASONS))
    if decision == "not_relevant" and reason is None:
        raise InvalidInput("reason_required", reasons=list(REASONS))
    for name in tags_ or ():
        tags.normalize(name)  # refuse a bad name before any decision is written
    ws = await workspace_id(session, workspace)
    own = await search_hits.owned_hit_ids(session, ws, hit_ids)
    kept_reason = reason if decision == "not_relevant" else None
    updated = await search_hits.bulk_review_hits(session, ws, list(own), decision, kept_reason, None)
    if tags_:
        await tags.tag_hits(session, ws, tags_, list(own))
    return ReviewResult(updated=updated, skipped=[h for h in hit_ids if h not in own])


async def import_hit(
    session: AsyncSession, workspace: str, hit_id: uuid.UUID, tags_: list[str] | None = None
) -> hit_import.ImportResult:
    ws = await workspace_id(session, workspace)
    if hit_id not in await search_hits.owned_hit_ids(session, ws, [hit_id]):
        raise NotFound("hit_not_found", hit_id=str(hit_id))
    if tags_:
        await tags.tag_hits(session, ws, tags_, [hit_id])
    async with source_clients.open_providers(session) as providers:
        imported = await hit_import.import_hits(session, providers, ws, [hit_id])
    for paper_id in imported.paper_ids:
        await queue.enqueue("ingest_paper", str(paper_id))
    return imported


DIRECTIONS = {"backward": (True, False), "forward": (False, True), "both": (True, True)}
VERDICTS = ("include", "exclude")


@dataclass(frozen=True)
class EligibilityView:
    paper_id: uuid.UUID
    run_id: uuid.UUID
    verdict: str | None
    reason: str | None
    assessed_at: datetime | None


async def snowball(
    session: AsyncSession, workspace: str, seed_paper_ids: list[uuid.UUID], direction: str
) -> snowball_run.SnowballResult:
    if direction not in DIRECTIONS:
        raise InvalidInput(f"direction is one of {', '.join(DIRECTIONS)}")
    if not seed_paper_ids:
        raise InvalidInput("Give at least one seed paper.")
    backward, forward = DIRECTIONS[direction]
    ws = await workspace_id(session, workspace)
    async with source_clients.open_providers(session) as providers:
        return await snowball_run.snowball(
            session, providers, ws, seed_paper_ids, [], snowball_run.Directions(backward, forward)
        )


async def set_eligibility(
    session: AsyncSession, workspace: str, paper_id: uuid.UUID, run_id: uuid.UUID, verdict: str,
    reason: str | None = None,
) -> EligibilityView:
    if verdict not in VERDICTS:
        raise InvalidInput("invalid_decision", verdicts=list(VERDICTS))
    ws = await workspace_id(session, workspace)
    row = await workspace_search.set_eligibility(session, ws, paper_id, run_id, verdict, reason)
    return EligibilityView(
        row.paper_id, row.search_run_id, row.stage2_status, row.stage2_exclude_reason, row.assessed_at
    )


async def get_prisma(
    session: AsyncSession, workspace: str, run_id: uuid.UUID | None = None
) -> prisma_export.PrismaExport:
    return await prisma_export.prisma_export(session, await workspace_id(session, workspace), run_id)
