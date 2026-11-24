"""Snowballing from seed papers: their references and citing works from Semantic Scholar, stored as hits."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search import discovery, hit_links
from app.core.search.batch_fetch import HitOrigin, _store_candidates_as_hits
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
class Directions:
    """Which way a hop goes from each seed: backward to what it cites, forward to what cites it."""

    backward: bool
    forward: bool

    def kinds(self) -> list[str]:
        """The link kinds asked for, cites first."""
        return [kind for flag, kind in ((self.backward, "cites"), (self.forward, "cited_by")) if flag]


@dataclass(frozen=True)
class SnowballResult:
    new_hits: int
    skipped_seeds: list[uuid.UUID] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


async def _snowball_from_s2(
    providers: Providers, doi: str | None, title: str, directions: Directions
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
    if directions.backward:
        try:
            cites = await semantic_scholar.references(providers.client("semantic_scholar"), key, SNOWBALL_REFS_CAP)
        except httpx.HTTPError as exc:
            errors["semantic_scholar_backward"] = str(exc)
        else:
            if cites is None:
                return None
            out["backward"] = [from_s2(p) for p in cites]
    if directions.forward:
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


@dataclass(frozen=True)
class _Seed:
    """One seed of a hop: an imported library paper or a not-yet-imported workspace hit."""

    id: uuid.UUID
    kind: str  # "paper" | "hit"
    title: str  # shown in the run's stats
    doi: str | None  # what Semantic Scholar is asked about, with lookup_title
    lookup_title: str | None  # None: a hit without an ExternalRef, nothing to look up
    hit_id: uuid.UUID | None  # the seed's hit, parent of the new hits (None for a hand-added paper that has none)
    paper_id: uuid.UUID | None  # the library paper (None for a hit seed)


def _seed_entry(
    seed: _Seed, found: dict[str, int] | None = None, new: dict[str, int] | None = None, skipped: str | None = None,
    error: str | None = None, errors: dict[str, str] | None = None,
) -> dict:
    """One seed's line in stats_json["snowball"]["seeds"]; counts are keyed by link kind (cites / cited_by).
    `errors` is keyed by link kind too; `done` lists the kinds that came back without error; `hit_id` is the
    seed's hit (None for a hand-added paper that has none)."""
    zero = {"cites": 0, "cited_by": 0}
    by_kind = {**{k: None for k in zero}, **(errors or {})}
    return {
        "id": str(seed.id), "kind": seed.kind, "title": seed.title, "found": {**zero, **(found or {})},
        "new": {**zero, **(new or {})}, "skipped": skipped, "error": error,
        "errors": by_kind, "done": [k for k in (found or {}) if by_kind[k] is None],
        "hit_id": str(seed.hit_id) if seed.hit_id else None,
    }


def _kind_errors(direction_errors: dict[str, str]) -> dict[str, str]:
    return {_ERROR_KEY_KINDS[key]: message for key, message in direction_errors.items()}


def _whole_seed_errors(message: str, directions: Directions) -> dict[str, str]:
    """A failure before any direction ran counts against every direction that was asked for."""
    return {kind: message for kind in directions.kinds()}


async def _store_hop(
    session: AsyncSession, run: WorkspaceSearchRun, found: dict[str, list[Candidate]], seed: _Seed
) -> dict[str, int]:
    """Stores one seed's per-direction candidates as hits, each linked to the seed (its hit, or else the bare paper),
    one level below it. Returns the number of newly added hits per link kind."""
    level = await hit_links.level_of(session, seed.hit_id) if seed.hit_id else 0
    # ponytail: no seed_hit_id column on WorkspaceSearchHit — seed_paper_id stays unset for a hit-seeded
    # hop; the parent is recorded in workspace_hit_links instead.
    new: dict[str, int] = {}
    for direction, candidates in found.items():
        source_method, kind = _DIRECTION_KINDS[direction]
        origin = HitOrigin(
            source_method, kind, seed_paper_id=seed.paper_id, snowball_round=level + 1, parent_hit_id=seed.hit_id,
            parent_paper_id=None if seed.hit_id else seed.paper_id,
        )
        stored = await _store_candidates_as_hits(session, run, {"semantic_scholar": candidates}, origin)
        new[kind] = stored.new_hits
    return new


def _snowball_query_text(first_title: str | None, seed_count: int) -> str:
    more = f" and {seed_count - 1} more" if seed_count > 1 else ""
    return f'Snowball from "{first_title or "?"}"{more}'


async def _paper_seed(session: AsyncSession, workspace_id: uuid.UUID, paper_id: uuid.UUID) -> _Seed:
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
    return _Seed(paper_id, "paper", paper.title, paper.doi, paper.title, parent_hit_id, paper_id)


async def _hit_seed(session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID) -> _Seed:
    hit = await session.get(WorkspaceSearchHit, hit_id)
    if hit is None or hit.workspace_id != workspace_id:
        raise NotFound(f"hit {hit_id} not found in workspace {workspace_id}")
    ref = await session.get(ExternalRef, hit.external_ref_id) if hit.external_ref_id else None
    if ref is None:
        return _Seed(hit_id, "hit", hit.normalized_title, None, None, hit_id, None)
    return _Seed(hit_id, "hit", ref.title, ref.doi, ref.title, hit_id, None)


async def _seeds(
    session: AsyncSession, workspace_id: uuid.UUID, paper_ids: list[uuid.UUID], hit_ids: list[uuid.UUID]
):
    """Papers first, then hits, each looked up only when its turn comes."""
    for paper_id in paper_ids:
        yield await _paper_seed(session, workspace_id, paper_id)
    for hit_id in hit_ids:
        yield await _hit_seed(session, workspace_id, hit_id)


async def _hop(
    session: AsyncSession, providers: Providers, run: WorkspaceSearchRun, seed: _Seed, directions: Directions
) -> tuple[dict, int, dict[str, str]]:
    """One seed's hop: its stats entry, the number of new hits, and the errors to report for the run."""
    if seed.lookup_title is None:
        return _seed_entry(seed, skipped=NOT_IN_S2), 0, {}
    try:
        result = await _snowball_from_s2(providers, seed.doi, seed.lookup_title, directions)
    except httpx.HTTPError as exc:
        # A failure before either direction's own try/except could run (e.g. the s2_key title-match lookup
        # itself 429ing) — not a per-direction error, so no direction-specific key to give it.
        entry = _seed_entry(seed, error=str(exc), errors=_whole_seed_errors(str(exc), directions))
        return entry, 0, {"semantic_scholar": str(exc)}
    if result is None:
        return _seed_entry(seed, skipped=NOT_IN_S2), 0, {}
    found, direction_errors = result
    new = await _store_hop(session, run, found, seed)
    entry = _seed_entry(
        seed, _found_counts(found), new, error=_joined(direction_errors), errors=_kind_errors(direction_errors)
    )
    return entry, sum(new.values()), direction_errors


async def snowball(
    session: AsyncSession, providers: Providers, workspace_id: uuid.UUID, seed_paper_ids: list[uuid.UUID],
    seed_hit_ids: list[uuid.UUID], directions: Directions,
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

    entries: list[dict] = []
    skipped: list[uuid.UUID] = []
    errors: dict[str, str] = {}
    new_hits = 0
    async for seed in _seeds(session, workspace_id, seed_paper_ids, seed_hit_ids):
        entry, added, seed_errors = await _hop(session, providers, run, seed, directions)
        entries.append(entry)
        skipped += [seed.id] if entry["skipped"] else []
        errors.update(seed_errors)
        new_hits += added

    if entries:
        run.query_text = _snowball_query_text(entries[0]["title"], len(entries))
    run.stats_json = {"snowball": {"seeds": entries, "directions": directions.kinds()}}
    await session.commit()
    return SnowballResult(new_hits=new_hits, skipped_seeds=skipped, errors=errors)
