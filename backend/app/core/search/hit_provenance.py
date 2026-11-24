"""Where each hit came from: the tree of searches and snowball hops that found it, and the paths to one hit."""

import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy import all_, any_, bindparam, exists, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search import search_run_results
from app.core.search.hit_links import MAX_DEPTH
from app.domain.errors import NotFound
from app.models import Paper
from app.models.provenance import WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun
from app.schemas.search_tree import LevelStats, ProvBranch, ProvenanceOut, ProvLink, ProvNode, ProvRoot

REASON_CHARS = 160


def _short(text: str | None) -> str | None:
    return text if text is None or len(text) <= REASON_CHARS else text[: REASON_CHARS - 1] + "…"


HAND = "root:hand"
_MIN = datetime.min.replace(tzinfo=timezone.utc)
PATHS_STEP_BUDGET = 10_000


class _Edge(NamedTuple):
    parent: str
    child: str
    kind: str
    run_id: uuid.UUID | None
    created_at: datetime | None


def _array(ids):
    return bindparam(None, list(ids), type_=ARRAY(PG_UUID(as_uuid=True)))


def _in(column, ids):
    """`column = ANY(:ids)`: one bound parameter however many ids (asyncpg caps a statement at 32,767)."""
    return column == any_(_array(ids))


def _unknown(run_id: uuid.UUID) -> str:
    return f"run:{run_id}:unknown"


async def _runs(session: AsyncSession, workspace_id: uuid.UUID) -> dict[uuid.UUID, WorkspaceSearchRun]:
    rows = await session.scalars(select(WorkspaceSearchRun).where(WorkspaceSearchRun.workspace_id == workspace_id))
    return {run.id: run for run in rows}


def _seeds(runs) -> list[tuple[dict, uuid.UUID | None]]:
    """Every snowball seed entry in run order, with its hit id when it has one."""
    out = []
    for run in sorted(runs.values(), key=lambda r: r.started_at):
        for seed in ((run.stats_json or {}).get("snowball") or {}).get("seeds", []):
            try:
                hit_id = uuid.UUID(seed["hit_id"]) if seed.get("hit_id") else None
            except ValueError:
                hit_id = None
            out.append((seed, hit_id))
    return out


async def _default_scope(session, workspace_id, runs) -> list[set[uuid.UUID]]:
    """Snowball-reached, decided, branched, snowballed-from or unlinked-legacy hits (never the search-only mass), in
    priority groups: seeds and snowball-reached, relevant, branched, other decided (excluded last)."""
    link, hit = WorkspaceHitLink, WorkspaceSearchHit
    reached: set[uuid.UUID] = set()
    for child, parent in await session.execute(
        select(link.child_hit_id, link.parent_hit_id).where(link.workspace_id == workspace_id, link.kind != "search")
    ):
        reached.update(i for i in (child, parent) if i)
    reached.update(h for _, h in _seeds(runs) if h)
    reached.update(await session.scalars(select(hit.id).where(
        hit.workspace_id == workspace_id, hit.source_method.like("snowball%"),
        ~exists().where(link.child_hit_id == hit.id))))
    decided = {i: s for i, s in await session.execute(
        select(hit.id, hit.stage1_status).where(hit.workspace_id == workspace_id, hit.stage1_status.is_not(None)))}
    branched = set(await session.scalars(select(WorkspaceBranchState.hit_id).where(
        WorkspaceBranchState.workspace_id == workspace_id, WorkspaceBranchState.hit_id.is_not(None))))
    return [
        reached, {i for i, s in decided.items() if s == "relevant"}, branched, set(decided),
    ]


async def _capped(session, workspace_id, groups: list[set[uuid.UUID]], cap: int) -> tuple[set[uuid.UUID], bool]:
    """Take the groups in order up to `cap` ids; inside a group that does not fit, the earliest-seen first."""
    ids: set[uuid.UUID] = set()
    dropped = False
    for group in groups:
        new = group - ids
        room = cap - len(ids)
        if len(new) > room:
            dropped = True
            new = set(await session.scalars(
                select(WorkspaceSearchHit.id).where(_in(WorkspaceSearchHit.id, new))
                .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id).limit(max(room, 0))))
        ids |= new
    return ids, dropped


async def _with_ancestors(session, workspace_id, ids: set[uuid.UUID]):
    """The ids plus every hit above them, and all links whose child is one of those hits."""
    seen, frontier, links = set(ids), set(ids), []
    while frontier:
        rows = (await session.scalars(select(WorkspaceHitLink).where(
            WorkspaceHitLink.workspace_id == workspace_id, _in(WorkspaceHitLink.child_hit_id, frontier)))).all()
        links.extend(rows)
        frontier = {p for r in rows if (p := r.parent_hit_id) is not None and p not in seen}
        seen |= frontier
    return seen, links


async def _graph(session, workspace_id, ids, runs, extra_papers=()):
    """(hits, papers, edges): scoped hits with their refs, the bare papers used as parents, and the links collapsed
    to one edge per (parent, child, kind), earliest first (spec call 2)."""
    seen, links = await _with_ancestors(session, workspace_id, ids)
    hits = {}
    if seen:
        rows = await session.execute(
            select(WorkspaceSearchHit, ExternalRef.title, ExternalRef.year)
            .outerjoin(ExternalRef, ExternalRef.id == WorkspaceSearchHit.external_ref_id)
            .where(WorkspaceSearchHit.workspace_id == workspace_id, _in(WorkspaceSearchHit.id, seen)))
        hits = {h.id: (h, title or h.normalized_title, year) for h, title, year in rows}
    paper_ids = {lk.parent_paper_id for lk in links if lk.parent_paper_id} | set(extra_papers)
    papers = {}
    if paper_ids:
        papers = {p.id: p for p in await session.scalars(select(Paper).where(_in(Paper.id, paper_ids)))}
    started = {rid: r.started_at for rid, r in runs.items()}
    edges, linked, refound = [], set(), []
    for lk in links:
        if lk.child_hit_id not in hits or (lk.parent_hit_id and lk.parent_hit_id not in hits):
            continue
        linked.add(lk.child_hit_id)
        if lk.run_id != hits[lk.child_hit_id][0].run_id:
            refound.append(str(lk.child_hit_id))  # a raw link from a run that did not first store the hit
        if lk.kind == "search":
            parent = f"root:{lk.run_id}"
        elif lk.parent_hit_id:
            parent = str(lk.parent_hit_id)
        elif lk.parent_paper_id in papers:
            parent = f"paper:{lk.parent_paper_id}"
            edges.append(_Edge(HAND, parent, "hand", None, None))
        else:
            continue
        edges.append(_Edge(parent, str(lk.child_hit_id), lk.kind, lk.run_id, lk.created_at))
    for hid, (h, _, _) in hits.items():  # no link at all: legacy data
        if hid in linked:
            continue
        if h.source_method.startswith("snowball"):
            kind = "cited_by" if h.source_method == "snowball_forward" else "cites"
            edges.append(_Edge(_unknown(h.run_id), str(hid), kind, h.run_id, h.first_seen_at))
        else:
            edges.append(_Edge(f"root:{h.run_id}", str(hid), "search", h.run_id, h.first_seen_at))
    edges.sort(key=lambda e: (e.created_at or _MIN, started.get(e.run_id, _MIN), e.parent))
    first: dict[tuple, _Edge] = {}
    for e in edges:
        first.setdefault((e.parent, e.child, e.kind), e)
    return hits, papers, list(first.values()), refound


def _levels(nodes: set[str], edges: list[_Edge]) -> dict[str, int]:
    """Breadth-first from the roots; a node keeps the first level it gets (spec call 3)."""
    children = defaultdict(list)
    level: dict[str, int] = {}
    queue = deque()
    for e in edges:
        if e.parent.startswith("root:") and not e.parent.endswith(":unknown") and e.child not in level:
            level[e.child] = 0
            queue.append(e.child)
        elif not e.parent.startswith("root:"):
            children[e.parent].append(e.child)
    for n in nodes:  # synthetic "parent not recorded" nodes are level 0 too
        if n.endswith(":unknown") and n not in level:
            level[n] = 0
            queue.append(n)
    while queue:
        node = queue.popleft()
        for kid in children[node]:
            if kid not in level:
                level[kid] = level[node] + 1
                queue.append(kid)
    return {n: level.get(n, 0) for n in nodes}


def _tree_roots(nodes: set[str], edges: list[_Edge], level: dict[str, int]) -> dict[str, str | None]:
    """The root each node hangs under, following its primary (earliest, one level up) link."""
    primary: dict[str, str] = {}
    for e in edges:  # edges are earliest-first
        from_root = e.parent.startswith("root:") and level[e.child] == 0
        if e.child not in primary and (from_root or level.get(e.parent, -2) == level[e.child] - 1):
            primary[e.child] = e.parent
    out = {}
    for n in nodes:
        cur = n
        for _ in range(MAX_DEPTH + 2):
            up = primary.get(cur)
            if up is None or up.startswith("root:"):
                out[n] = up if up and not up.endswith(":unknown") else None
                break
            cur = up
        else:
            out[n] = None
    return out


@dataclass(frozen=True)
class _SeedState:
    """What each seed's hops did, keyed by node id."""

    done: dict[str, set[str]]  # the directions already run
    zero: dict[str, str | None]  # found nothing: the error or skip reason ("" = ran cleanly); None = found some
    skipped: set[str]  # seeds the latest run could not find in Semantic Scholar: nothing left to run


@dataclass(frozen=True)
class _Tree:
    node_ids: set[str]
    edges: list[_Edge]
    level: dict[str, int]
    hits: dict
    papers: dict
    branches: dict[str, WorkspaceBranchState]
    seeds: _SeedState
    incoming: dict[str, int]  # links into each node


async def _scoped_ids(
    session: AsyncSession, workspace_id: uuid.UUID, runs: dict, all_hits_run_id: uuid.UUID | None, cap: int
) -> tuple[set[uuid.UUID], bool]:
    """The default scope's hits, plus `all_hits_run_id`'s hits up to `cap`; and whether a cap cut either short."""
    ids, truncated = await _capped(session, workspace_id, await _default_scope(session, workspace_id, runs), cap)
    if all_hits_run_id is None:
        return ids, truncated
    extra = list(await session.scalars(
        select(WorkspaceSearchHit.id).where(
            WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.run_id == all_hits_run_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id).limit(cap + 1)))
    return ids | set(extra[:cap]), truncated or len(extra) > cap


def _bare_papers(seeds: list) -> list[uuid.UUID]:
    """Hand-added paper seeds (no hit): zero-found ones are still nodes."""
    bare = []
    for seed, hit_id in seeds:
        if seed.get("kind") == "paper" and hit_id is None:
            try:
                bare.append(uuid.UUID(seed["id"]))
            except ValueError:
                pass
    return bare


def _hand_edges(bare: list[uuid.UUID], papers: dict, edges: list[_Edge]) -> list[_Edge]:
    """A link from "Added by hand" to each held bare paper nothing else links to."""
    held = [p for p in dict.fromkeys(bare) if p in papers]
    linked = {e.child for e in edges}
    return [_Edge(HAND, f"paper:{p}", "hand", None, None) for p in held if f"paper:{p}" not in linked]


def _seed_state(seeds: list) -> _SeedState:
    done: dict[str, set[str]] = defaultdict(set)
    zero: dict[str, str | None] = {}
    skipped: set[str] = set()
    for seed, hit_id in seeds:
        key = str(hit_id) if hit_id else f"paper:{seed.get('id')}"
        done[key].update(seed.get("done") or [])
        found_any = sum((seed.get("found") or {}).values())
        zero[key] = None if found_any else (seed.get("error") or seed.get("skipped") or "")
        (skipped.add if seed.get("skipped") else skipped.discard)(key)
    return _SeedState(done, zero, skipped)


async def _branches(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, WorkspaceBranchState]:
    rows = (await session.scalars(
        select(WorkspaceBranchState).where(WorkspaceBranchState.workspace_id == workspace_id))).all()
    return {(str(b.hit_id) if b.hit_id else f"paper:{b.paper_id}"): b for b in rows}


def _node(tree: _Tree, nid: str) -> ProvNode:
    b = tree.branches.get(nid)
    branch = ProvBranch(state=b.state, directions=b.directions, reason=b.reason) if b else None
    if nid.startswith("paper:"):
        paper = tree.papers[uuid.UUID(nid[6:])]
        node = dict(title=paper.title, year=paper.year, paper_id=paper.id)
    elif nid.endswith(":unknown"):
        node = dict(title="Parent not recorded")
    else:
        h, title, year = tree.hits[uuid.UUID(nid)]
        node = dict(title=title, year=year, decision=h.stage1_status, suggestion=h.suggestion,
                    relevance=h.suggestion_relevance, reason=_short(h.suggestion_note), paper_id=h.paper_id)
    return ProvNode(
        id=nid, level=tree.level[nid], branch=branch, snowballed=sorted(tree.seeds.done.get(nid, ())),
        paths=tree.incoming.get(nid, 0), zero_found_error=tree.seeds.zero.get(nid), **node)


async def provenance(
    session: AsyncSession, workspace_id: uuid.UUID, *, all_hits_run_id: uuid.UUID | None = None, cap: int = 2000
) -> ProvenanceOut:
    """The tree of how every paper reached the workspace. Default scope: hits reached by snowball, decided,
    branched, snowballed from, or with no recorded parent, plus their ancestors. `all_hits_run_id` adds that run's
    hits up to `cap`."""
    runs = await _runs(session, workspace_id)
    ids, truncated = await _scoped_ids(session, workspace_id, runs, all_hits_run_id, cap)
    seeds = _seeds(runs)
    bare = _bare_papers(seeds)
    hits, papers, edges, refound = await _graph(session, workspace_id, ids, runs, bare)
    edges = edges + _hand_edges(bare, papers, edges)
    linked = {e.child for e in edges}
    node_ids = {str(h) for h in hits} | {f"paper:{p}" for p in papers if f"paper:{p}" in linked}
    node_ids |= {e.parent for e in edges if e.parent.endswith(":unknown")}
    level = _levels(node_ids, edges)
    tree = _Tree(
        node_ids, edges, level, hits, papers, await _branches(session, workspace_id), _seed_state(seeds),
        Counter(e.child for e in edges),
    )
    nodes = [_node(tree, nid) for nid in sorted(node_ids, key=lambda n: (level[n], n))]
    links = [ProvLink(parent=e.parent, child=e.child, kind=e.kind, run_id=e.run_id, created_at=e.created_at)
             for e in edges]
    return ProvenanceOut(
        nodes=nodes, links=links, roots=await _roots(session, workspace_id, runs, tree),
        levels=_level_stats(nodes, edges, level, runs, refound, tree.seeds.skipped), truncated=truncated)


async def _roots(session: AsyncSession, workspace_id: uuid.UUID, runs: dict, tree: _Tree) -> list[ProvRoot]:
    counts = dict((await session.execute(
        select(WorkspaceHitLink.run_id, func.count()).where(
            WorkspaceHitLink.workspace_id == workspace_id, WorkspaceHitLink.kind == "search")
        .group_by(WorkspaceHitLink.run_id))).all())
    legacy = await session.execute(  # database_search hits with no link at all still belong to their run's root
        select(WorkspaceSearchHit.run_id, func.count()).where(
            WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.source_method.not_like("snowball%"),
            ~exists().where(WorkspaceHitLink.child_hit_id == WorkspaceSearchHit.id),
        ).group_by(WorkspaceSearchHit.run_id))
    for run_id, n in legacy:
        counts[run_id] = counts.get(run_id, 0) + n
    hidden = dict((await session.execute(  # excluded search hits the cap left off the tree
        select(WorkspaceSearchHit.run_id, func.count()).where(
            WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.stage1_status == "not_relevant",
            WorkspaceSearchHit.source_method.not_like("snowball%"), WorkspaceSearchHit.id != all_(_array(tree.hits)))
        .group_by(WorkspaceSearchHit.run_id))).all())
    on_tree = Counter(root for root in _tree_roots(tree.node_ids, tree.edges, tree.level).values() if root)
    labels = await search_run_results.run_labels(session, runs.values())
    roots = [
        ProvRoot(
            id=f"root:{run.id}", label=labels[run.id], hit_count=counts.get(run.id, 0),
            on_tree=on_tree[f"root:{run.id}"], excluded_hidden=hidden.get(run.id, 0))
        for run in sorted(runs.values(), key=lambda r: r.started_at)
        if counts.get(run.id) or on_tree[f"root:{run.id}"]
    ]
    if on_tree[HAND]:
        papers = sum(n.startswith("paper:") for n in tree.node_ids)
        roots.append(ProvRoot(id=HAND, label="Added by hand", hit_count=papers, on_tree=on_tree[HAND]))
    return roots


def _level_stats(
    nodes: list[ProvNode], edges: list[_Edge], level, runs, refound, skipped: set[str]
) -> list[LevelStats]:
    deepest = max(level.values(), default=0)
    out = []
    for lv in range(deepest + 1):
        here = [n for n in nodes if n.level == lv]
        found = sum(not n.id.endswith(":unknown") for n in here)  # synthetic parents are not finds
        into = [e for e in edges if level.get(e.child) == lv]
        known = sum(level.get(c) == lv for c in refound)
        go = [n for n in here if n.branch and n.branch.state == "go_further"]
        screened = all(_screened(n) for n in here)
        run_everywhere = all(n.id in skipped or set(n.branch.directions) <= set(n.snowballed) for n in go)
        saturated = False
        if lv == deepest:
            snow = [e for e in into if e.kind != "search" and e.run_id in runs]
            if snow:
                last = max(runs[e.run_id].started_at for e in snow)
                brought = {e.child for e in snow if runs[e.run_id].started_at == last}
                kids = [n for n in here if n.id in brought]
                saturated = bool(kids) and all(_screened(n) for n in kids) and not any(
                    n.decision == "relevant" for n in kids)
        out.append(LevelStats(
            level=lv, found=found, already_known=known,
            included=sum(n.decision == "relevant" for n in here), go_further=len(go),
            stopped=sum(bool(n.branch and n.branch.state == "stopped") for n in here),
            done=screened and run_everywhere, saturated=saturated))
    return out


def _screened(node: ProvNode) -> bool:
    """Bare papers and synthetic parents have nothing to screen."""
    return node.id.startswith("paper:") or node.id.endswith(":unknown") or node.decision is not None


async def paths_to(
    session: AsyncSession, workspace_id: uuid.UUID, hit_id: uuid.UUID, limit: int = 20
) -> list[list[ProvLink]]:
    """Every root-to-hit path, shortest first. Walks up from the hit over simple paths only (no repeated node).
    ponytail: the search stops after PATHS_STEP_BUDGET expansions, so a hit buried in a dense
    cross-linked graph may return fewer than `limit` paths."""
    owned = await session.scalar(select(WorkspaceSearchHit.id).where(
        WorkspaceSearchHit.id == hit_id, WorkspaceSearchHit.workspace_id == workspace_id))
    if owned is None:
        raise NotFound(f"hit {hit_id} not found")
    _, _, edges, _ = await _graph(session, workspace_id, {hit_id}, await _runs(session, workspace_id))
    above = defaultdict(list)
    for e in edges:
        above[e.child].append(e)
    found: list[tuple[_Edge, ...]] = []
    queue = deque([(str(hit_id), (), frozenset({str(hit_id)}))])
    for _ in range(PATHS_STEP_BUDGET):  # breadth-first over partial paths, so complete ones come out shortest first
        if not queue or len(found) >= limit:
            break
        node, tail, visited = queue.popleft()
        if not above[node]:
            found.append(tail)
        queue.extend((e.parent, (e, *tail), visited | {e.parent}) for e in above[node] if e.parent not in visited)
    return [
        [ProvLink(parent=e.parent, child=e.child, kind=e.kind, run_id=e.run_id, created_at=e.created_at) for e in p]
        for p in found
    ]
