"""Snowball tree: the provenance reader (nodes, links, roots, levels, paths) and its routes."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import NotFound
from app.core.hit_links import level_of, paths_to, provenance
from app.models import Paper
from app.models.provenance import WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _workspace(session):
    workspace = Workspace(name=f"prov-{uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    return workspace


async def _run(session, workspace, *, minutes=0, stats=None, query="bert"):
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text=query, filters_json={}, query_overrides_json={},
        sources_json=["arxiv"], status="exhausted", started_at=BASE + timedelta(minutes=minutes),
        stats_json=stats or {},
    )
    session.add(run)
    await session.flush()
    return run


async def _hit(session, workspace, run, title, *, method="database_search", status=None, n=0):
    ref = ExternalRef(title=title, year=2020)
    session.add(ref)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method=method,
        normalized_title=title.lower(), first_seen_at=BASE + timedelta(minutes=n), stage1_status=status,
    )
    session.add(hit)
    await session.flush()
    return hit


async def _link(session, workspace, run, child, parent=None, kind="search", *, paper=None, at=0):
    session.add(WorkspaceHitLink(
        workspace_id=workspace.id, child_hit_id=child.id, parent_hit_id=parent.id if parent else None,
        parent_paper_id=paper.id if paper else None, run_id=run.id, kind=kind,
        created_at=BASE + timedelta(minutes=at),
    ))
    await session.flush()


async def _chain(session):
    """search -> A (relevant) --cites--> B --cited_by--> C."""
    ws = await _workspace(session)
    run = await _run(session, ws)
    snow = await _run(session, ws, minutes=5)
    a = await _hit(session, ws, run, "A", status="relevant")
    b = await _hit(session, ws, snow, "B", method="snowball_backward", n=5)
    c = await _hit(session, ws, snow, "C", method="snowball_forward", n=6)
    await _link(session, ws, run, a)
    await _link(session, ws, snow, b, a, "cites", at=5)
    await _link(session, ws, snow, c, b, "cited_by", at=6)
    return ws, run, snow, a, b, c


def _by_id(out):
    return {n.id: n for n in out.nodes}


async def test_tree_shape_and_levels(session):
    ws, run, _, a, b, c = await _chain(session)
    out = await provenance(session, ws.id)
    nodes = _by_id(out)
    assert [nodes[str(h.id)].level for h in (a, b, c)] == [0, 1, 2]
    assert nodes[str(a.id)].title == "A" and nodes[str(a.id)].year == 2020
    assert nodes[str(a.id)].decision == "relevant"
    (root,) = out.roots
    assert (root.id, root.hit_count, root.on_tree) == (f"root:{run.id}", 1, 3)
    kinds = {(link.parent, link.child, link.kind) for link in out.links}
    assert (f"root:{run.id}", str(a.id), "search") in kinds and (str(a.id), str(b.id), "cites") in kinds
    assert not out.truncated


async def test_levels_survive_a_citation_cycle(session):
    ws, _, snow, a, b, c = await _chain(session)
    await _link(session, ws, snow, a, c, "cites", at=7)
    out = await provenance(session, ws.id)
    nodes = _by_id(out)
    assert [nodes[str(h.id)].level for h in (a, b, c)] == [0, 1, 2]
    assert nodes[str(a.id)].paths == 2


async def test_same_edge_from_two_runs_is_one_path(session):
    ws, _, snow, a, b, _ = await _chain(session)
    again = await _run(session, ws, minutes=9)
    await _link(session, ws, again, b, a, "cites", at=9)
    out = await provenance(session, ws.id)
    assert _by_id(out)[str(b.id)].paths == 1
    assert len([x for x in out.links if x.child == str(b.id)]) == 1


async def test_default_scope_skips_unscreened_search_only_hits(session):
    ws, run, _, a, b, c = await _chain(session)
    for i in range(50):
        h = await _hit(session, ws, run, f"noise {i}", n=i)
        await _link(session, ws, run, h)
    out = await provenance(session, ws.id)
    assert {n.id for n in out.nodes} == {str(a.id), str(b.id), str(c.id)}
    assert out.roots[0].hit_count == 51


async def test_all_hits_run_is_capped(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    for i in range(50):
        h = await _hit(session, ws, run, f"h{i}", n=i)
        await _link(session, ws, run, h)
    out = await provenance(session, ws.id, all_hits_run_id=run.id, cap=10)
    assert len(out.nodes) == 10 and out.truncated
    full = await provenance(session, ws.id, all_hits_run_id=run.id)
    assert len(full.nodes) == 50 and not full.truncated


async def test_default_scope_is_capped_with_seeds_and_snowball_first_excluded_last(session):
    ws, run, _, a, b, c = await _chain(session)
    for i in range(30):
        h = await _hit(session, ws, run, f"out {i}", status="not_relevant", n=i)
        await _link(session, ws, run, h)
    for i in range(3):
        h = await _hit(session, ws, run, f"rel {i}", status="relevant", n=40 + i)
        await _link(session, ws, run, h)
    out = await provenance(session, ws.id, cap=8)
    ids = {n.id for n in out.nodes}
    assert out.truncated and len(ids) == 8
    assert {str(a.id), str(b.id), str(c.id)} <= ids  # the snowball chain survives
    titles = {n.title for n in out.nodes}
    assert {"rel 0", "rel 1", "rel 2"} <= titles  # relevant before excluded
    (root,) = (r for r in out.roots if r.id == f"root:{run.id}")
    assert root.excluded_hidden == 28  # 8 = 3 chain + 3 relevant + 2 of the 30 excluded
    full = await provenance(session, ws.id)
    assert not full.truncated and full.roots[0].excluded_hidden == 0


async def test_zero_found_seed_is_a_node_with_error(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    seed = await _hit(session, ws, run, "Seed")
    await _link(session, ws, run, seed)
    stats = {"snowball": {"directions": ["backward"], "seeds": [{
        "id": str(seed.id), "kind": "hit", "title": "Seed", "hit_id": str(seed.id),
        "found": {"cites": 0, "cited_by": 0}, "new": {"cites": 0, "cited_by": 0}, "skipped": None,
        "error": "S2 down", "errors": {"cites": "S2 down", "cited_by": None}, "done": ["cited_by"],
    }]}}
    await _run(session, ws, minutes=2, stats=stats)
    node = _by_id(await provenance(session, ws.id))[str(seed.id)]
    assert node.zero_found_error == "S2 down"
    assert node.snowballed == ["cited_by"]


async def test_clean_zero_found_seed_has_an_empty_error_not_none(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    seed = await _hit(session, ws, run, "Seed")
    await _link(session, ws, run, seed)
    stats = {"snowball": {"directions": ["backward"], "seeds": [{
        "id": str(seed.id), "kind": "hit", "title": "Seed", "hit_id": str(seed.id),
        "found": {"cites": 0, "cited_by": 0}, "new": {"cites": 0, "cited_by": 0}, "skipped": None,
        "error": None, "errors": {}, "done": ["cites", "cited_by"],
    }]}}
    await _run(session, ws, minutes=2, stats=stats)
    assert _by_id(await provenance(session, ws.id))[str(seed.id)].zero_found_error == ""


async def test_legacy_unknown_parent_node(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    legacy = await _hit(session, ws, run, "Old", method="snowball_backward")
    out = await provenance(session, ws.id)
    nodes = _by_id(out)
    unknown = f"run:{run.id}:unknown"
    assert nodes[unknown].level == 0 and nodes[str(legacy.id)].level == 1
    assert out.levels[0].found == 0  # the synthetic parent is not a find
    assert any(x.parent == unknown and x.child == str(legacy.id) for x in out.links)


async def test_hand_added_paper_root(session):
    ws, run, snow, a, b, _ = await _chain(session)
    paper = Paper(title="Hand paper")
    session.add(paper)
    await session.flush()
    kid = await _hit(session, ws, snow, "Kid", method="snowball_backward", n=8)
    await _link(session, ws, snow, kid, None, "cites", paper=paper, at=8)
    out = await provenance(session, ws.id)
    nodes = _by_id(out)
    assert nodes[f"paper:{paper.id}"].title == "Hand paper" and nodes[f"paper:{paper.id}"].level == 0
    assert nodes[str(kid.id)].level == 1
    hand = next(r for r in out.roots if r.id == "root:hand")
    assert (hand.hit_count, hand.on_tree) == (1, 2)


async def test_level_stats(session):
    ws, run, snow, a, b, c = await _chain(session)
    b.stage1_status = "relevant"
    # a is go_further both ways but only snowballed 'cites'; b is stopped; c is a re-find from the first run
    session.add_all([
        WorkspaceBranchState(workspace_id=ws.id, hit_id=a.id, state="go_further", directions=["cites", "cited_by"]),
        WorkspaceBranchState(workspace_id=ws.id, hit_id=b.id, state="stopped", directions=[]),
    ])
    run.stats_json = {"snowball": {"directions": ["backward"], "seeds": [{
        "id": str(a.id), "kind": "hit", "title": "A", "hit_id": str(a.id), "found": {"cites": 1, "cited_by": 0},
        "new": {"cites": 1, "cited_by": 0}, "errors": {}, "done": ["cites"],
    }]}}
    await session.flush()
    again = await _run(session, ws, minutes=9)
    await _link(session, ws, again, c, a, "cited_by", at=9)  # level 1 link whose child lives in `snow`
    c.stage1_status = "not_relevant"
    await session.flush()
    out = await provenance(session, ws.id)
    lv = {x.level: x for x in out.levels}
    assert (lv[0].found, lv[0].included, lv[0].go_further, lv[0].done) == (1, 1, 1, False)
    assert (lv[1].found, lv[1].already_known, lv[1].included, lv[1].stopped, lv[1].done) == (2, 1, 1, 1, True)
    assert lv[1].saturated and not lv[0].saturated  # the last run (again) brought only c, screened and not relevant
    assert not lv[0].done and lv[1].done


async def test_unscreened_deepest_level_is_neither_done_nor_saturated(session):
    ws, *_ = await _chain(session)
    deepest = (await provenance(session, ws.id)).levels[-1]
    assert (deepest.level, deepest.done, deepest.saturated) == (2, False, False)


async def test_screened_deepest_level_with_nothing_included_is_saturated_and_done(session):
    ws, _, _, a, b, c = await _chain(session)
    b.stage1_status, c.stage1_status = "not_relevant", "not_relevant"
    await session.flush()
    deepest = (await provenance(session, ws.id)).levels[-1]
    assert (deepest.level, deepest.done, deepest.saturated) == (2, True, True)
    c.stage1_status = "relevant"
    await session.flush()
    deepest = (await provenance(session, ws.id)).levels[-1]
    assert (deepest.done, deepest.saturated) == (True, False)


async def test_a_seed_not_found_in_semantic_scholar_counts_as_done(session):
    ws, run, snow, a, b, c = await _chain(session)
    for h in (b, c):
        h.stage1_status = "not_relevant"
    session.add(WorkspaceBranchState(workspace_id=ws.id, hit_id=a.id, state="go_further", directions=["cites"]))
    snow.stats_json = {"snowball": {"directions": ["backward"], "seeds": [{
        "id": str(a.id), "kind": "hit", "title": "A", "hit_id": str(a.id), "found": {"cites": 0, "cited_by": 0},
        "new": {"cites": 0, "cited_by": 0}, "skipped": "not_in_s2", "error": None, "errors": {}, "done": [],
    }]}}
    await session.flush()
    assert (await provenance(session, ws.id)).levels[0].done


async def test_paths_to_returns_every_route(session):
    ws, run, snow, a, b, c = await _chain(session)
    await _link(session, ws, snow, c, a, "cited_by", at=7)
    paths = await paths_to(session, ws.id, c.id)
    assert [len(p) for p in paths] == [2, 3]
    assert paths[0][0].parent == f"root:{run.id}" and paths[1][-1].child == str(c.id)
    with pytest.raises(NotFound):
        await paths_to(session, ws.id, uuid.uuid4())


async def test_provenance_levels_equal_level_of(session):
    ws, run, snow, a, b, c = await _chain(session)
    await _link(session, ws, snow, a, c, "cites", at=7)
    await _link(session, ws, snow, c, a, "cited_by", at=7)
    out = await provenance(session, ws.id)
    for hit in (a, b, c):
        assert _by_id(out)[str(hit.id)].level == await level_of(session, hit.id)


async def test_routes(client, session):
    ws, run, _, a, b, c = await _chain(session)
    await session.commit()
    res = await client.get(f"/api/workspaces/{ws.id}/search/provenance")
    assert res.status_code == 200 and len(res.json()["nodes"]) == 3
    res = await client.get(f"/api/workspaces/{ws.id}/search/provenance", params={"all_hits_run": str(run.id)})
    assert res.status_code == 200
    res = await client.get(f"/api/workspaces/{ws.id}/search/hits/{c.id}/paths")
    assert res.status_code == 200 and len(res.json()) == 1 and len(res.json()[0]) == 3


async def test_refound_edge_counts_as_already_known(session):
    ws, _, _, a, b, _ = await _chain(session)
    again = await _run(session, ws, minutes=9)
    await _link(session, ws, again, b, a, "cites", at=9)  # the same a->b edge, found again by a later run
    lv = {x.level: x for x in (await provenance(session, ws.id)).levels}
    assert lv[1].already_known == 1


async def test_dense_cyclic_graph_returns_quickly_shortest_first(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    hits = [await _hit(session, ws, run, f"d{i}", n=i) for i in range(20)]
    await _link(session, ws, run, hits[0])
    for i, child in enumerate(hits):
        for j, parent in enumerate(hits):
            if i != j:
                await _link(session, ws, run, child, parent, "cites", at=1)
    paths = await paths_to(session, ws.id, hits[19].id, limit=5)
    assert 0 < len(paths) <= 5
    assert [len(p) for p in paths] == sorted(len(p) for p in paths) and len(paths[0]) == 2


async def test_tie_break_runs_then_parent_id(session):
    ws = await _workspace(session)
    early = await _run(session, ws, minutes=0, query="early")
    late = await _run(session, ws, minutes=5, query="late")
    kid = await _hit(session, ws, late, "Kid")
    await _link(session, ws, late, kid, at=1)  # same created_at from both runs
    await _link(session, ws, early, kid, at=1)
    out = await provenance(session, ws.id, all_hits_run_id=late.id)
    assert [x.parent for x in out.links if x.child == str(kid.id)] == [f"root:{early.id}", f"root:{late.id}"]
    assert {r.id: r.on_tree for r in out.roots} == {f"root:{early.id}": 1, f"root:{late.id}": 0}

    p1 = await _hit(session, ws, early, "P1", status="relevant")
    p2 = await _hit(session, ws, early, "P2", status="relevant")
    for p in (p1, p2):
        await _link(session, ws, early, p)
    other = await _hit(session, ws, late, "Other")
    for p in (p2, p1):
        await _link(session, ws, late, other, p, "cites", at=3)
    out = await provenance(session, ws.id)
    assert [x.parent for x in out.links if x.child == str(other.id)] == sorted([str(p1.id), str(p2.id)])


async def test_two_search_links_are_two_paths(session):
    ws = await _workspace(session)
    r1, r2 = await _run(session, ws), await _run(session, ws, minutes=3)
    h = await _hit(session, ws, r1, "Twice")
    await _link(session, ws, r1, h)
    await _link(session, ws, r2, h, at=3)
    paths = await paths_to(session, ws.id, h.id)
    assert sorted(p[0].parent for p in paths) == sorted([f"root:{r1.id}", f"root:{r2.id}"])


async def test_legacy_search_hit_counts_toward_root(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    await _hit(session, ws, run, "NoLink", status="relevant")
    (root,) = (await provenance(session, ws.id)).roots
    assert (root.hit_count, root.on_tree) == (1, 1)


async def test_paths_route_404_for_another_workspaces_hit(client, session):
    ws, *_ = await _chain(session)
    _, _, _, _, _, foreign = await _chain(session)
    await session.commit()
    res = await client.get(f"/api/workspaces/{ws.id}/search/hits/{foreign.id}/paths")
    assert res.status_code == 404


async def test_skipped_seed_shows_why_it_found_nothing(session):
    ws = await _workspace(session)
    run = await _run(session, ws)
    seed = await _hit(session, ws, run, "Seed")
    await _link(session, ws, run, seed)
    stats = {"snowball": {"directions": ["cites"], "seeds": [{
        "id": str(seed.id), "kind": "hit", "title": "Seed", "hit_id": str(seed.id),
        "found": {"cites": 0, "cited_by": 0}, "new": {"cites": 0, "cited_by": 0},
        "skipped": "not found in Semantic Scholar", "error": None, "errors": {"cites": None, "cited_by": None}, "done": [],
    }]}}
    await _run(session, ws, minutes=2, stats=stats)
    node = _by_id(await provenance(session, ws.id))[str(seed.id)]
    assert node.zero_found_error == "not found in Semantic Scholar"
