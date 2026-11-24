"""Snowballing from seed papers: their references and citing works from Semantic Scholar, stored as hits."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search import discovery, hit_links
from app.core.search.batch_fetch import _store_candidates_as_hits
from app.core.search.from_indexes import from_s2
from app.core.search.source_clients import Providers
from app.core.workspaces import workspaces
from app.domain.candidates import Candidate
from app.domain.errors import Conflict, NotFound
from app.models import Paper, workspace_papers
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import semantic_scholar

# Own constants, deliberately not references.py's REFS_CAP/CITING_CAP — the two features stay decoupled even
# though the values happen to match today.
SNOWBALL_REFS_CAP = 500
SNOWBALL_CITING_CAP = 200


@dataclass(frozen=True)
class SnowballResult:
    new_hits: int
    skipped_seeds: list[uuid.UUID] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


async def _snowball_from_s2(
    providers: Providers, doi: str | None, title: str, backward: bool, forward: bool
) -> tuple[dict[str, list[Candidate]], dict[str, str]] | None:
    """None when Semantic Scholar doesn't know the doi/title (a 404 on any direction asked for — same signal
    references.py's _from_semantic_scholar uses). Mirrors that function, scoped to just the requested
    direction(s). Takes doi/title directly rather than a Paper, so this serves either an imported library paper or
    a not-yet-imported hit's own ExternalRef (snowball's point, below).

    Otherwise returns whatever direction(s) succeeded, plus a per-direction message for whichever raised
    httpx.HTTPError (e.g. an unauthenticated S2 429 — spec §16's default, not an edge case). Each direction is
    tried and caught independently: one direction erroring must never drop the other direction's already-fetched
    hits (fix-round finding — /citations 429ing used to wipe out a successful /references call for the same
    seed, because the exception used to propagate out of this whole function to snowball()'s per-seed
    try/except)."""
    key = await discovery.s2_key(providers.client("semantic_scholar"), doi, title)
    if key is None:
        return None
    out: dict[str, list[Candidate]] = {}
    errors: dict[str, str] = {}
    if backward:
        try:
            cites = await semantic_scholar.references(providers.client("semantic_scholar"), key, SNOWBALL_REFS_CAP)
        except httpx.HTTPError as exc:
            errors["semantic_scholar_backward"] = str(exc)
        else:
            if cites is None:
                return None
            out["backward"] = [from_s2(p) for p in cites]
    if forward:
        try:
            cited_by = await semantic_scholar.citations(providers.client("semantic_scholar"), key, SNOWBALL_CITING_CAP)
        except httpx.HTTPError as exc:
            errors["semantic_scholar_forward"] = str(exc)
        else:
            if cited_by is None:
                return None
            out["forward"] = [from_s2(p) for p in cited_by]
    return out, errors


NOT_IN_S2 = "not found in Semantic Scholar"


def _found_counts(found: dict[str, list[Candidate]]) -> dict[str, int]:
    return {_DIRECTION_KINDS[direction][1]: len(candidates) for direction, candidates in found.items()}


def _joined(direction_errors: dict[str, str]) -> str | None:
    return "; ".join(direction_errors.values()) or None


_ERROR_KEY_KINDS = {"semantic_scholar_backward": "cites", "semantic_scholar_forward": "cited_by"}


_DIRECTION_KINDS = {"backward": ("snowball_backward", "cites"), "forward": ("snowball_forward", "cited_by")}


def _seed_entry(
    seed_id: uuid.UUID, kind: str, title: str, found: dict[str, int] | None = None, new: dict[str, int] | None = None,
    skipped: str | None = None, error: str | None = None, hit_id: uuid.UUID | None = None,
    errors: dict[str, str] | None = None,
) -> dict:
    """One seed's line in stats_json["snowball"]["seeds"]; counts are keyed by link kind (cites / cited_by).
    `errors` is keyed by link kind too; `done` lists the kinds that came back without error; `hit_id` is the
    seed's hit (None for a hand-added paper that has none)."""
    zero = {"cites": 0, "cited_by": 0}
    by_kind = {**{k: None for k in zero}, **(errors or {})}
    return {
        "id": str(seed_id), "kind": kind, "title": title, "found": {**zero, **(found or {})},
        "new": {**zero, **(new or {})}, "skipped": skipped, "error": error,
        "errors": by_kind, "done": [k for k in (found or {}) if by_kind[k] is None],
        "hit_id": str(hit_id) if hit_id else None,
    }


def _kind_errors(direction_errors: dict[str, str]) -> dict[str, str]:
    return {_ERROR_KEY_KINDS[key]: message for key, message in direction_errors.items()}


def _whole_seed_errors(message: str, backward: bool, forward: bool) -> dict[str, str]:
    """A failure before any direction ran counts against every direction that was asked for."""
    return {kind: message for flag, kind in ((backward, "cites"), (forward, "cited_by")) if flag}


async def _store_hop(
    session: AsyncSession, run: WorkspaceSearchRun, found: dict[str, list[Candidate]], snowball_round: int,
    parent_hit_id: uuid.UUID | None, parent_paper_id: uuid.UUID | None, seed_paper_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Stores one seed's per-direction candidates as hits, each linked to the seed (a hit, or a bare paper).
    Returns the number of newly added hits per link kind."""
    new: dict[str, int] = {}
    for direction, candidates in found.items():
        source_method, kind = _DIRECTION_KINDS[direction]
        added, _ = await _store_candidates_as_hits(
            session, run, source_method, {"semantic_scholar": candidates}, seed_paper_id=seed_paper_id,
            snowball_round=snowball_round, kind=kind, parent_hit_id=parent_hit_id, parent_paper_id=parent_paper_id,
        )
        new[kind] = added
    return new


def _snowball_query_text(first_title: str | None, seed_count: int) -> str:
    more = f" and {seed_count - 1} more" if seed_count > 1 else ""
    return f'Snowball from "{first_title or "?"}"{more}'


async def snowball(
    session: AsyncSession, providers: Providers, workspace_id: uuid.UUID, seed_paper_ids: list[uuid.UUID],
    seed_hit_ids: list[uuid.UUID], backward: bool, forward: bool,
) -> SnowballResult:
    """One hop, from each seed, via Semantic Scholar. A seed can be an already-imported library paper
    (seed_paper_ids) or a not-yet-imported workspace hit (seed_hit_ids) — citation-graph discovery only ever
    needs a doi/title (discovery.s2_key), which a hit's own ExternalRef already has, so snowballing from it
    never requires a free PDF to have been found first (that's import_hits' separate concern: acquiring a copy
    of the paper, not discovering what it cites/is cited by). New hits land in the same pool as database-search
    hits (spec P8, §9), tagged snowball_backward/snowball_forward, deduped by (workspace_id, external_ref_id)
    through the same `_store_candidates_as_hits` path search_batch uses — a seed's reference already in the pool
    keeps its existing screening state.

    WorkspaceSearchHit.run_id is NOT NULL, and a snowball hop isn't a polling "run" — a lightweight run row is
    created once per call (status="exhausted" immediately: there's nothing to page) and used as every resulting
    hit's run_id, which also gives PRISMA's later per-run reporting a real row to point at.

    Semantic Scholar entirely off (providers.client("semantic_scholar") is None) raises Conflict once, up
    front, mirroring references.fetch()'s "nothing enabled" check — with no source configured at all there's no
    useful per-seed distinction to make (every seed would just land in skipped_seeds for the same reason)."""
    await workspaces.require_writable(session, workspace_id)
    if providers.client("semantic_scholar") is None:
        raise Conflict("Semantic Scholar is off. Turn it on in Settings → Paper sources to snowball.")

    run = WorkspaceSearchRun(
        workspace_id=workspace_id,
        query_text=_snowball_query_text(None, len(seed_paper_ids) + len(seed_hit_ids)),
        filters_json={}, query_overrides_json={}, sources_json=["semantic_scholar"], status="exhausted",
        started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()

    skipped: list[uuid.UUID] = []
    errors: dict[str, str] = {}
    new_hits = 0
    entries: list[dict] = []
    for paper_id in seed_paper_ids:
        member = (
            await session.execute(
                select(workspace_papers.c.paper_id).where(
                    workspace_papers.c.workspace_id == workspace_id, workspace_papers.c.paper_id == paper_id
                )
            )
        ).first()
        if member is None:
            raise NotFound(f"paper {paper_id} not in workspace {workspace_id}")
        paper = await session.get(Paper, paper_id)
        parent_hit_id = await hit_links.seed_parent(session, workspace_id, paper_id)
        try:
            result = await _snowball_from_s2(providers, paper.doi, paper.title, backward, forward)
        except httpx.HTTPError as exc:
            # A failure before either direction's own try/except could run (e.g. the s2_key title-match lookup
            # itself 429ing) — not a per-direction error, so no direction-specific key to give it.
            errors["semantic_scholar"] = str(exc)
            entries.append(_seed_entry(
                paper_id, "paper", paper.title, error=str(exc), hit_id=parent_hit_id,
                errors=_whole_seed_errors(str(exc), backward, forward),
            ))
            continue
        if result is None:
            skipped.append(paper_id)
            entries.append(_seed_entry(paper_id, "paper", paper.title, skipped=NOT_IN_S2, hit_id=parent_hit_id))
            continue
        found, direction_errors = result
        errors.update(direction_errors)
        level = await hit_links.level_of(session, parent_hit_id) if parent_hit_id else 0
        new = await _store_hop(
            session, run, found, level + 1, parent_hit_id, None if parent_hit_id else paper_id, seed_paper_id=paper_id
        )
        new_hits += sum(new.values())
        entries.append(_seed_entry(
            paper_id, "paper", paper.title, _found_counts(found), new, error=_joined(direction_errors),
            hit_id=parent_hit_id, errors=_kind_errors(direction_errors),
        ))

    for hit_id in seed_hit_ids:
        hit = await session.get(WorkspaceSearchHit, hit_id)
        if hit is None or hit.workspace_id != workspace_id:
            raise NotFound(f"hit {hit_id} not found in workspace {workspace_id}")
        ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
        title = ref.title if ref else hit.normalized_title
        if ref is None:
            skipped.append(hit_id)
            entries.append(_seed_entry(hit_id, "hit", title, skipped=NOT_IN_S2, hit_id=hit_id))
            continue
        try:
            result = await _snowball_from_s2(providers, ref.doi, ref.title, backward, forward)
        except httpx.HTTPError as exc:
            errors["semantic_scholar"] = str(exc)
            entries.append(_seed_entry(
                hit_id, "hit", title, error=str(exc), hit_id=hit_id,
                errors=_whole_seed_errors(str(exc), backward, forward),
            ))
            continue
        if result is None:
            skipped.append(hit_id)
            entries.append(_seed_entry(hit_id, "hit", title, skipped=NOT_IN_S2, hit_id=hit_id))
            continue
        found, direction_errors = result
        errors.update(direction_errors)
        # ponytail: no seed_hit_id column on WorkspaceSearchHit — seed_paper_id stays unset for a hit-seeded
        # hop; the parent is recorded in workspace_hit_links instead.
        new = await _store_hop(session, run, found, await hit_links.level_of(session, hit_id) + 1, hit_id, None)
        new_hits += sum(new.values())
        entries.append(_seed_entry(
            hit_id, "hit", title, _found_counts(found), new, error=_joined(direction_errors), hit_id=hit_id,
            errors=_kind_errors(direction_errors),
        ))

    if entries:
        run.query_text = _snowball_query_text(entries[0]["title"], len(entries))
    directions = [kind for flag, kind in ((backward, "cites"), (forward, "cited_by")) if flag]
    run.stats_json = {"snowball": {"seeds": entries, "directions": directions}}
    await session.commit()
    return SnowballResult(new_hits=new_hits, skipped_seeds=skipped, errors=errors)
