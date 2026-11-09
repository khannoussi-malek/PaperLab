"""Snowball tree: record each path a search hit reached a workspace by (workspace_hit_links)."""

import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy import all_, any_, bindparam, exists, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import Paper
from app.models.provenance import WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun
from app.schemas.workspace_search import (
    LevelStats,
    ProvBranch,
    ProvenanceOut,
    ProvLink,
    ProvNode,
    ProvRoot,
)

MAX_DEPTH = 50


async def record_links(
    session: AsyncSession, run: WorkspaceSearchRun, child_hit_ids: list[uuid.UUID], kind: str,
    parent_hit_id: uuid.UUID | None, parent_paper_id: uuid.UUID | None,
) -> None:
    """One batched insert; a path already recorded is left alone. A hit is never linked to itself."""
    rows = [
        {
            "workspace_id": run.workspace_id, "child_hit_id": child, "parent_hit_id": parent_hit_id,
            "parent_paper_id": parent_paper_id, "run_id": run.id, "kind": kind,
        }
        for child in dict.fromkeys(child_hit_ids)
        if child != parent_hit_id
    ]
    if rows:
        await session.execute(pg_insert(WorkspaceHitLink).values(rows).on_conflict_do_nothing())


async def already_found_by_saved_search(
    session: AsyncSession, run: WorkspaceSearchRun, hit_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Of these hits, the ones an earlier run of this run's saved search already linked as a search hit."""
    rows = await session.scalars(
        select(WorkspaceHitLink.child_hit_id)
        .join(WorkspaceSearchRun, WorkspaceSearchRun.id == WorkspaceHitLink.run_id)
        .where(
            WorkspaceHitLink.child_hit_id.in_(hit_ids), WorkspaceHitLink.kind == "search",
            WorkspaceSearchRun.saved_search_id == run.saved_search_id, WorkspaceSearchRun.id != run.id,
        )
    )
    return set(rows)


async def seed_parent(session: AsyncSession, workspace_id: uuid.UUID, paper_id: uuid.UUID) -> uuid.UUID | None:
    """The earliest hit in the workspace that carries this paper, if any."""
    return await session.scalar(
        select(WorkspaceSearchHit.id)
        .where(WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.paper_id == paper_id)
        .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id)
        .limit(1)
    )


async def level_of(session: AsyncSession, hit_id: uuid.UUID) -> int:
    """How many hops a hit is from where it entered the workspace. Walks up breadth-first with a visited set (one
    query per depth), so a densely cross-linked graph costs one pass, not one per path. A hit with a `search` link
    is level 0 and not walked past; a link to a bare paper makes the hit one deeper than that paper; a hit with no
    links at all (legacy data) is level 0. No such hit within MAX_DEPTH: level 0."""
    best: int | None = None
    seen = {hit_id}
    frontier = [hit_id]
    for depth in range(MAX_DEPTH + 1):
        if not frontier or (best is not None and depth >= best):
            break
        rows = (await session.execute(
            select(
                WorkspaceHitLink.child_hit_id, WorkspaceHitLink.parent_hit_id,
                WorkspaceHitLink.parent_paper_id, WorkspaceHitLink.kind,
            ).where(WorkspaceHitLink.child_hit_id.in_(frontier))
        )).all()
        by_child: dict[uuid.UUID, list] = {h: [] for h in frontier}
        for row in rows:
            by_child[row.child_hit_id].append(row)
        nxt: list[uuid.UUID] = []
        for hit, links in by_child.items():
            if not links or any(link.kind == "search" for link in links):
                best = depth if best is None else min(best, depth)
                continue  # a root (or legacy hit): not walked past
            if any(link.parent_hit_id is None for link in links):  # a bare-paper parent counts as level 0
                best = depth + 1 if best is None else min(best, depth + 1)
            nxt.extend(
                p for link in links if (p := link.parent_hit_id) is not None and p not in seen and not seen.add(p)
            )
        frontier = nxt
    return best or 0


REASON_CHARS = 160


def _short(text: str | None) -> str | None:
    return text if text is None or len(text) <= REASON_CHARS else text[: REASON_CHARS - 1] + "…"


# ---- Provenance reader (the snowball tree) ----------------------------------------------------------------------

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


async def provenance(
    session: AsyncSession, workspace_id: uuid.UUID, *, all_hits_run_id: uuid.UUID | None = None, cap: int = 2000
) -> ProvenanceOut:
    """The tree of how every paper reached the workspace. Default scope: hits reached by snowball, decided,
    branched, snowballed from, or with no recorded parent, plus their ancestors. `all_hits_run_id` adds that run's
    hits up to `cap`."""
    runs = await _runs(session, workspace_id)
    ids, truncated = await _capped(session, workspace_id, await _default_scope(session, workspace_id, runs), cap)
    if all_hits_run_id is not None:
        extra = list(await session.scalars(
            select(WorkspaceSearchHit.id).where(
                WorkspaceSearchHit.workspace_id == workspace_id, WorkspaceSearchHit.run_id == all_hits_run_id)
            .order_by(WorkspaceSearchHit.first_seen_at, WorkspaceSearchHit.id).limit(cap + 1)))
        truncated = truncated or len(extra) > cap
        ids.update(extra[:cap])
    seeds = _seeds(runs)
    bare = []  # hand-added paper seeds (no hit): zero-found ones are still nodes
    for seed, hit_id in seeds:
        if seed.get("kind") == "paper" and hit_id is None:
            try:
                bare.append(uuid.UUID(seed["id"]))
            except ValueError:
                pass
    hits, papers, edges, refound = await _graph(session, workspace_id, ids, runs, bare)
    bare = [p for p in bare if p in papers]
    for p in bare:
        if not any(e.child == f"paper:{p}" for e in edges):
            edges.append(_Edge(HAND, f"paper:{p}", "hand", None, None))
    node_ids = {str(h) for h in hits} | {f"paper:{p}" for p in papers if any(e.child == f"paper:{p}" for e in edges)}
    node_ids |= {e.parent for e in edges if e.parent.endswith(":unknown")}
    level = _levels(node_ids, edges)
    branch_rows = (await session.scalars(
        select(WorkspaceBranchState).where(WorkspaceBranchState.workspace_id == workspace_id))).all()
    branches = {(str(b.hit_id) if b.hit_id else f"paper:{b.paper_id}"): b for b in branch_rows}
    done: dict[str, set[str]] = defaultdict(set)
    zero: dict[str, str | None] = {}
    skipped: set[str] = set()  # seeds the latest run could not find in Semantic Scholar: nothing left to run
    for seed, hit_id in seeds:
        key = str(hit_id) if hit_id else f"paper:{seed.get('id')}"
        done[key].update(seed.get("done") or [])
        if not sum((seed.get("found") or {}).values()):  # "" = ran cleanly and found nothing
            zero[key] = seed.get("error") or seed.get("skipped") or ""
        else:
            zero[key] = None
        (skipped.add if seed.get("skipped") else skipped.discard)(key)
    incoming: dict[str, int] = defaultdict(int)
    for e in edges:
        incoming[e.child] += 1

    nodes = []
    for nid in sorted(node_ids, key=lambda n: (level[n], n)):
        b = branches.get(nid)
        branch = ProvBranch(state=b.state, directions=b.directions, reason=b.reason) if b else None
        if nid.startswith("paper:"):
            paper = papers[uuid.UUID(nid[6:])]
            node = dict(title=paper.title, year=paper.year, paper_id=paper.id)
        elif nid.endswith(":unknown"):
            node = dict(title="Parent not recorded")
        else:
            h, title, year = hits[uuid.UUID(nid)]
            node = dict(title=title, year=year, decision=h.stage1_status, suggestion=h.suggestion,
                        relevance=h.suggestion_relevance, reason=_short(h.suggestion_note), paper_id=h.paper_id)
        nodes.append(ProvNode(
            id=nid, level=level[nid], branch=branch, snowballed=sorted(done.get(nid, ())), paths=incoming[nid],
            zero_found_error=zero.get(nid), **node))

    links = [ProvLink(parent=e.parent, child=e.child, kind=e.kind, run_id=e.run_id, created_at=e.created_at)
             for e in edges]
    return ProvenanceOut(
        nodes=nodes, links=links, roots=await _roots(session, workspace_id, runs, node_ids, edges, level, hits),
        levels=_level_stats(nodes, edges, level, runs, refound, skipped), truncated=truncated)


async def _roots(session, workspace_id, runs, node_ids, edges, level, hits) -> list[ProvRoot]:
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
            WorkspaceSearchHit.source_method.not_like("snowball%"), WorkspaceSearchHit.id != all_(_array(hits)))
        .group_by(WorkspaceSearchHit.run_id))).all())
    on_tree: dict[str, int] = defaultdict(int)
    for root in _tree_roots(node_ids, edges, level).values():
        if root:
            on_tree[root] += 1
    roots = []
    for run in sorted(runs.values(), key=lambda r: r.started_at):
        rid = f"root:{run.id}"
        if counts.get(run.id) or on_tree[rid]:
            roots.append(ProvRoot(
                id=rid, label=run.query_text, hit_count=counts.get(run.id, 0), on_tree=on_tree[rid],
                excluded_hidden=hidden.get(run.id, 0)))
    if on_tree[HAND]:
        papers = sum(n.startswith("paper:") for n in node_ids)
        roots.append(ProvRoot(id=HAND, label="Added by hand", hit_count=papers, on_tree=on_tree[HAND]))
    return roots


def _level_stats(nodes: list[ProvNode], edges: list[_Edge], level, runs, refound, skipped: set[str]) -> list[LevelStats]:
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
