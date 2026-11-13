"""A workspace's live screening as a package carries it (M35c, screening.json version 2): the runs with their stats and
paging state, every hit with its reference, stage-1 decision and AI suggestion, the stage-2 eligibility, the snowball
links and the branch states. Every id leaves as a package key (r1, h1, p1); papers outside the workspace that the
screening names are listed too, marked `member: false`. Nothing secret: a cursor keeps only its paging state, and
stats and last errors pass redact().

The import side (`rebuild`) is added below this export half."""

import uuid
from dataclasses import dataclass

from sqlalchemy import any_, bindparam, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import search_run_results
from app.core.redact import redact
from app.models import Paper
from app.models.provenance import WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import (
    SearchRunEligibility,
    WorkspaceSearchCursor,
    WorkspaceSearchHit,
    WorkspaceSearchRun,
)

VERSION = 2
CURSOR_STATE = ("value", "errors", "paused", "retry_after", "disabled")  # paging state only; nothing else leaves


@dataclass(frozen=True)
class Live:
    runs: list[WorkspaceSearchRun]
    cursors: dict[uuid.UUID, list[WorkspaceSearchCursor]]
    hits: list[tuple[WorkspaceSearchHit, ExternalRef | None]]  # first seen first
    eligibility: list[SearchRunEligibility]
    links: list[WorkspaceHitLink]
    branches: list[WorkspaceBranchState]


def _iso(moment) -> str | None:
    return moment.isoformat() if moment else None


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _array(ids):
    return bindparam(None, list(ids), type_=ARRAY(PG_UUID(as_uuid=True)))


async def load(session: AsyncSession, workspace_id: uuid.UUID, runs: list[WorkspaceSearchRun]) -> Live:
    """Every screening row of the workspace, read once. `runs` are the workspace's runs, in start order."""
    run_ids = [run.id for run in runs]
    hit_rows = await session.execute(
        select(WorkspaceSearchHit, ExternalRef)
        .outerjoin(ExternalRef, WorkspaceSearchHit.external_ref_id == ExternalRef.id)
        .where(WorkspaceSearchHit.workspace_id == workspace_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
    )
    return Live(
        runs=runs,
        cursors=await search_run_results.cursors_by_run(session, run_ids),
        hits=[(hit, ref) for hit, ref in hit_rows.all()],
        eligibility=list(
            (
                await session.scalars(
                    select(SearchRunEligibility).where(SearchRunEligibility.search_run_id.in_(run_ids))
                )
            ).all()
        ),
        links=list(
            (await session.scalars(select(WorkspaceHitLink).where(WorkspaceHitLink.workspace_id == workspace_id))).all()
        ),
        branches=list(
            (
                await session.scalars(
                    select(WorkspaceBranchState).where(WorkspaceBranchState.workspace_id == workspace_id)
                )
            ).all()
        ),
    )


def _seed_papers(live: Live) -> set[uuid.UUID]:
    """The snowball seeds' ids that are not hits: a seed paper (a library paper or a hand-added one)."""
    hit_ids = {hit.id for hit, _ in live.hits}
    seeds = {_uuid((seed or {}).get("id")) for run in live.runs for seed in _seeds_of(run)}
    return {s for s in seeds if s is not None and s not in hit_ids}


def _seeds_of(run: WorkspaceSearchRun) -> list[dict]:
    return ((run.stats_json or {}).get("snowball") or {}).get("seeds", [])


def referenced_papers(live: Live) -> set[uuid.UUID]:
    """Every paper the screening names, members or not: a hit's, a seed's, an eligibility's, a link's, a branch's."""
    ids = {h.paper_id for h, _ in live.hits} | {h.seed_paper_id for h, _ in live.hits}
    ids |= {e.paper_id for e in live.eligibility} | {b.paper_id for b in live.branches}
    ids |= {link.parent_paper_id for link in live.links} | _seed_papers(live)
    return {i for i in ids if i is not None}


async def outside_papers(session: AsyncSession, live: Live, members: set[uuid.UUID]) -> list[Paper]:
    """The referenced papers that are not workspace members, by title. A seed id that names no paper is dropped."""
    wanted = referenced_papers(live) - members
    if not wanted:
        return []
    rows = await session.scalars(select(Paper).where(Paper.id == any_(_array(wanted))))
    return sorted(rows, key=lambda paper: (paper.title or "", str(paper.id)))


def _hit_keys(live: Live) -> dict[uuid.UUID, str]:
    return {hit.id: f"h{number}" for number, (hit, _) in enumerate(live.hits, start=1)}


def _cursor_state(cursor_json: dict | None) -> dict:
    return {k: v for k, v in (cursor_json or {}).items() if k in CURSOR_STATE}


def _seed(seed: dict, hit_keys: dict, paper_keys: dict) -> dict:
    """A seed's line without its database ids: its hit and its paper by key (either may be None)."""
    rest = {k: v for k, v in seed.items() if k not in ("id", "hit_id")}
    return rest | {
        "hit": hit_keys.get(_uuid(seed.get("hit_id"))),
        "paper": paper_keys.get(_uuid(seed.get("id"))),
    }


def _stats(stats: dict | None, hit_keys: dict, paper_keys: dict) -> dict:
    out = dict(stats or {})
    if "warnings" in out:
        out["warnings"] = [{**w, "message": redact(str(w.get("message", "")))} for w in out["warnings"]]
    if "snowball" in out:
        snowball = out["snowball"] or {}
        seeds = [_seed(s, hit_keys, paper_keys) for s in snowball.get("seeds", [])]
        out["snowball"] = {**snowball, "seeds": seeds}
    return out


def _run_row(run, run_keys, labels, hit_keys, paper_keys, cursors) -> dict:
    return {
        "key": run_keys[run.id],
        "query": labels[run.id],
        "sources": run.sources_json,
        "filters": run.filters_json,
        "query_overrides": run.query_overrides_json or {},
        "status": run.status,
        "started_at": _iso(run.started_at),
        "stopped_at": _iso(run.stopped_at),
        "stats": _stats(run.stats_json, hit_keys, paper_keys),
        "cursors": [
            {
                "source": c.source,
                "exhausted": c.exhausted,
                "cursor": _cursor_state(c.cursor_json),
                "last_error": search_run_results.short_error(c.last_error),
            }
            for c in sorted(cursors, key=lambda c: c.source)
        ],
    }


def _ai_suggestion(hit: WorkspaceSearchHit) -> dict | None:
    if hit.suggestion is None:
        return None
    return {
        "ai": True,
        "suggestion": hit.suggestion,
        "reason": hit.suggestion_reason,
        "note": hit.suggestion_note,
        "model": hit.suggestion_model,
        "relevance": hit.suggestion_relevance,
        "confidence": hit.suggestion_confidence,
        "quotes": hit.suggestion_quotes,
        "flags": hit.suggestion_flags,
        "prompt_version": hit.suggestion_prompt_version,
        "suggested_at": _iso(hit.suggested_at),
    }


def _hit_row(key, hit, ref, run_keys, paper_keys, stage2) -> dict:
    """The hit with its reference's metadata (a reference gone from the library keeps the hit's own title)."""
    verdict = stage2.get((hit.paper_id, hit.run_id)) if hit.paper_id else None
    return {
        "key": key, "run": run_keys[hit.run_id],
        "title": ref.title if ref else hit.normalized_title, "doi": ref.doi if ref else None,
        "external_ids": (ref.external_ids if ref else None) or {}, "authors": (ref.authors if ref else None) or [],
        "year": ref.year if ref else None, "venue": ref.venue if ref else None,
        "abstract": ref.abstract if ref else None, "source_type": ref.source_type if ref else None,
        "published_doi": ref.published_doi if ref else None, "published_venue": ref.published_venue if ref else None,
        "paper": paper_keys.get(hit.paper_id), "source_method": hit.source_method,
        "seed_paper": paper_keys.get(hit.seed_paper_id), "snowball_round": hit.snowball_round,
        "first_seen_at": _iso(hit.first_seen_at), "acquisition_status": hit.acquisition_status,
        "priority": hit.priority, "topic_fit": hit.topic_fit,
        "stage1": {"status": hit.stage1_status, "exclude_reason": hit.stage1_exclude_reason, "note": hit.stage1_note},
        "stage1_decided_at": _iso(hit.stage1_decided_at),
        "stage2": {"status": verdict.stage2_status, "exclude_reason": verdict.stage2_exclude_reason}
        if verdict is not None else None,
        "ai_suggestion": _ai_suggestion(hit),
    }  # fmt: skip


def document(live: Live, workspace: Workspace, run_keys: dict, labels: dict, paper_keys: dict) -> dict:
    """screening.json version 2. `paper_keys` covers every member and every referenced outside paper."""
    hit_keys = _hit_keys(live)
    stage2 = {(e.paper_id, e.search_run_id): e for e in live.eligibility}
    return {
        "version": VERSION,
        "runs": [
            _run_row(run, run_keys, labels, hit_keys, paper_keys, live.cursors.get(run.id, [])) for run in live.runs
        ],
        "hits": [_hit_row(hit_keys[hit.id], hit, ref, run_keys, paper_keys, stage2) for hit, ref in live.hits],
        "eligibility": [
            {
                "paper": paper_keys[e.paper_id],
                "run": run_keys[e.search_run_id],
                "stage2_status": e.stage2_status,
                "exclude_reason": e.stage2_exclude_reason,
                "assessed_at": _iso(e.assessed_at),
            }
            for e in live.eligibility
        ],
        "links": [
            {
                "child_hit": hit_keys[link.child_hit_id],
                "parent_hit": hit_keys.get(link.parent_hit_id),
                "parent_paper": paper_keys.get(link.parent_paper_id),
                "kind": link.kind,
                "run": run_keys[link.run_id],
            }
            for link in live.links
        ],
        "branches": [
            {
                "hit": hit_keys.get(b.hit_id),
                "paper": paper_keys.get(b.paper_id),
                "state": b.state,
                "directions": b.directions or [],
                "reason": b.reason,
                "set_by": b.set_by,
            }
            for b in live.branches
        ],
        "workspace": {
            "screening_criteria": workspace.screening_criteria,
            "screening_ranked_used": workspace.screening_ranked_used,
        },
    }
