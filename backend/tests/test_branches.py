"""Branch states (snowball tree): hand choices, screening defaults, and the PUT route."""

import uuid

import pytest
from sqlalchemy import select

from app.core import branches, screening, workspace_search
from app.core.errors import InvalidInput, NotFound
from app.models.provenance import WorkspaceBranchState
from app.schemas.workspace_search import HitReviewUpdate
from tests.screening_pool import make_pool

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

BOTH = ["cites", "cited_by"]


async def _row(session, hit):
    return await session.scalar(select(WorkspaceBranchState).where(WorkspaceBranchState.hit_id == hit.id))


async def test_set_branch_go_further_and_back_to_undecided(session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    out = await branches.set_branch(
        session, workspace.id, hit_id=hit.id, state="go_further",
        directions=["cited_by", "cites", "cites"], reason="ignored",
    )
    assert (out.hit_id, out.state, out.directions, out.reason) == (hit.id, "go_further", BOTH, None)
    stopped = await branches.set_branch(
        session, workspace.id, hit_id=hit.id, state="stopped", directions=[], reason="off topic"
    )
    assert (stopped.state, stopped.reason) == ("stopped", "off topic")
    undone = await branches.set_branch(session, workspace.id, hit_id=hit.id, state=None, directions=[], reason=None)
    assert undone.state is None
    assert await _row(session, hit) is None


async def test_set_branch_rejects_bad_input(session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    _, (foreign,) = await make_pool(session, [("z", None)])

    async def call(**kw):
        args = {"hit_id": hit.id, "state": "stopped", "directions": [], "reason": None} | kw
        return await branches.set_branch(session, workspace.id, **args)

    with pytest.raises(InvalidInput):
        await call(paper_id=uuid.uuid4())  # both targets
    with pytest.raises(InvalidInput):
        await call(hit_id=None)  # neither
    with pytest.raises(InvalidInput):
        await call(state="maybe")
    with pytest.raises(InvalidInput):
        await call(state="go_further", directions=["sideways"])
    with pytest.raises(InvalidInput):
        await call(state="go_further", directions=[])
    with pytest.raises(InvalidInput):
        await call(reason="x" * 201)
    with pytest.raises(NotFound):
        await call(hit_id=foreign.id)
    with pytest.raises(NotFound):
        await call(hit_id=None, paper_id=uuid.uuid4())


async def test_including_a_hit_defaults_to_go_further_both_ways(session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    await workspace_search.review_hit(session, hit.id, workspace.id, HitReviewUpdate(stage1_status="relevant"))
    row = await _row(session, hit)
    assert (row.state, row.directions) == ("go_further", BOTH)


async def test_excluding_defaults_to_stopped(session):
    workspace, (a, b) = await make_pool(session, [("a", None)] * 2)
    await workspace_search.bulk_review_hits(session, workspace.id, [a.id, b.id], "not_relevant", "wrong_topic", None)
    assert (await _row(session, a)).state == "stopped" and (await _row(session, b)).state == "stopped"


async def test_accepted_suggestion_sets_default(session):
    workspace, (inc, exc) = await make_pool(session, [("a", None)] * 2)
    inc.suggestion = "include"
    exc.suggestion, exc.suggestion_reason = "exclude", "wrong_topic"
    await session.flush()
    await screening.accept_suggestions(session, workspace.id, [inc.id, exc.id])
    assert (await _row(session, inc)).state == "go_further"
    assert (await _row(session, exc)).state == "stopped"


async def test_screening_default_never_overwrites_a_hand_choice(session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    await branches.set_branch(session, workspace.id, hit_id=hit.id, state="stopped", directions=[], reason=None)
    await workspace_search.review_hit(session, hit.id, workspace.id, HitReviewUpdate(stage1_status="relevant"))
    assert (await _row(session, hit)).state == "stopped"


async def test_branch_route_round_trip(client, session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    await session.commit()
    url = f"/api/workspaces/{workspace.id}/search/branch"
    resp = await client.put(url, json={"hit_id": str(hit.id), "state": "go_further", "directions": ["cites"]})
    assert resp.status_code == 200
    assert resp.json() == {
        "hit_id": str(hit.id), "paper_id": None, "state": "go_further", "directions": ["cites"], "reason": None,
    }
    resp = await client.put(url, json={"hit_id": str(hit.id), "state": None})
    assert resp.json()["state"] is None
    bad = await client.put(url, json={"hit_id": str(hit.id), "state": "go_further"})
    assert bad.status_code == 422
    missing = await client.put(url, json={"hit_id": str(hit.id)})  # state is required, null clears
    assert missing.status_code == 422


async def test_flipped_decision_updates_a_screening_default(session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    await workspace_search.review_hit(session, hit.id, workspace.id, HitReviewUpdate(stage1_status="relevant"))
    await workspace_search.review_hit(
        session, hit.id, workspace.id,
        HitReviewUpdate(stage1_status="not_relevant", stage1_exclude_reason="wrong_topic"),
    )
    await session.refresh(await _row(session, hit))
    row = await _row(session, hit)
    assert (row.state, row.directions, row.set_by) == ("stopped", [], "screening")


async def test_undone_decision_clears_a_screening_default(session):
    workspace, (hit, owned) = await make_pool(session, [("a", None)] * 2)
    for h in (hit, owned):
        await workspace_search.review_hit(session, h.id, workspace.id, HitReviewUpdate(stage1_status="relevant"))
    await branches.set_branch(
        session, workspace.id, hit_id=owned.id, state="go_further", directions=["cites"], reason=None
    )
    for h in (hit, owned):
        await workspace_search.review_hit(session, h.id, workspace.id, HitReviewUpdate(stage1_status=None))
    assert await _row(session, hit) is None
    assert (await _row(session, owned)).set_by == "owner"


async def test_default_skips_hits_from_another_workspace(session):
    workspace, _ = await make_pool(session, [("a", None)])
    _, (foreign,) = await make_pool(session, [("z", None)])
    await branches.default_branch_on_decision(session, workspace.id, [foreign.id], "relevant")
    assert await _row(session, foreign) is None


async def test_maybe_clears_a_screening_default(session):
    workspace, (hit,) = await make_pool(session, [("a", None)])
    await workspace_search.review_hit(session, hit.id, workspace.id, HitReviewUpdate(stage1_status="relevant"))
    assert (await _row(session, hit)).state == "go_further"
    await workspace_search.review_hit(session, hit.id, workspace.id, HitReviewUpdate(stage1_status="maybe"))
    assert await _row(session, hit) is None


async def test_branch_on_a_papers_hit_is_stored_on_the_hit(session):
    from app.core import workspaces
    from app.models import Paper

    workspace, (hit,) = await make_pool(session, [("a", None)])
    paper = Paper(title="P", file_path="/p.pdf")
    session.add(paper)
    await session.flush()
    await workspaces.add_paper(session, workspace.id, paper.id)
    hit.paper_id = paper.id
    await session.flush()

    out = await branches.set_branch(
        session, workspace.id, paper_id=paper.id, state="stopped", directions=[], reason="no"
    )
    assert (out.hit_id, out.paper_id) == (hit.id, None)
    assert (await _row(session, hit)).state == "stopped"
    rows = (await session.scalars(select(WorkspaceBranchState).where(
        WorkspaceBranchState.workspace_id == workspace.id))).all()
    assert [r.paper_id for r in rows] == [None]


# --- Snowball next (Task 8) ---
from app.core import snowball_next  # noqa: E402
from tests.test_snowball_links import (  # noqa: E402,F401  (fixtures)
    _s2_with, _seed_hit, _workspace_and_run, edge_providers, fake_providers,
)


async def test_snowball_next_lists_unrun_directions(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run, title="Seed Alpha")
    fresh = await _seed_hit(session, workspace, run, title="Seed Beta")
    stopped = await _seed_hit(session, workspace, run, title="Seed Gamma")
    for hit in (seed, fresh):
        await branches.set_branch(session, workspace.id, hit_id=hit.id, state="go_further", directions=BOTH, reason=None)
    await branches.set_branch(session, workspace.id, hit_id=stopped.id, state="stopped", directions=[], reason=None)
    await workspace_search.snowball(session, edge_providers, workspace.id, [], [seed.id], backward=True, forward=False)

    items = {i.hit_id: i for i in await snowball_next.snowball_next(session, workspace.id)}
    assert set(items) == {seed.id, fresh.id}
    assert items[seed.id].directions_left == ["cited_by"] and items[seed.id].title == "Seed Alpha"
    assert items[fresh.id].directions_left == BOTH


async def test_run_snowball_next_empties_the_list(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    one = await _seed_hit(session, workspace, run, title="Seed Alpha")
    two = await _seed_hit(session, workspace, run, title="Seed Beta")
    await branches.set_branch(session, workspace.id, hit_id=one.id, state="go_further", directions=BOTH, reason=None)
    await branches.set_branch(session, workspace.id, hit_id=two.id, state="go_further", directions=["cites"], reason=None)

    out = await snowball_next.run_snowball_next(session, edge_providers, workspace.id)
    assert out.new_hits > 0
    assert await snowball_next.snowball_next(session, workspace.id) == []


async def test_snowball_next_leaves_out_a_seed_not_found_in_semantic_scholar(session):
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run, title="Seed Alpha")
    await branches.set_branch(session, workspace.id, hit_id=seed.id, state="go_further", directions=BOTH, reason=None)
    entry = workspace_search._seed_entry(seed.id, "hit", "Seed Alpha", skipped=workspace_search.NOT_IN_S2, hit_id=seed.id)
    run.stats_json = {"snowball": {"seeds": [entry], "directions": BOTH}}
    await session.commit()
    assert await snowball_next.snowball_next(session, workspace.id) == []


async def test_run_snowball_next_takes_a_batch_and_reports_the_rest(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    for i in range(30):
        hit = await _seed_hit(session, workspace, run, title=f"Seed {i:02d}")
        await branches.set_branch(session, workspace.id, hit_id=hit.id, state="go_further", directions=["cites"], reason=None)

    out = await snowball_next.run_snowball_next(session, edge_providers, workspace.id)
    assert out.remaining == 30 - snowball_next.SNOWBALL_NEXT_BATCH == 5
    assert len(await snowball_next.snowball_next(session, workspace.id)) == 5


async def test_remaining_counts_a_batch_item_whose_direction_errored(session, fake_providers):
    from dataclasses import replace

    import httpx

    from app.providers import discovery_fake

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/citations"):
            return httpx.Response(429)
        if request.url.path.endswith("/references"):
            return httpx.Response(200, json={"offset": 0, "data": []})
        return discovery_fake._handle(request)

    client = _s2_with(handle)
    providers = replace(fake_providers, clients={**fake_providers.clients, "semantic_scholar": client})
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run, title="Rate limited")
    await branches.set_branch(session, workspace.id, hit_id=seed.id, state="go_further", directions=BOTH, reason=None)

    try:
        out = await snowball_next.run_snowball_next(session, providers, workspace.id)
    finally:
        await client.aclose()
    assert out.remaining == 1
    (item,) = await snowball_next.snowball_next(session, workspace.id)
    assert item.directions_left == ["cited_by"]


async def test_a_branch_on_a_paper_that_left_the_workspace_is_not_offered_and_can_be_cleared(session, edge_providers):
    from app.core import workspaces
    from app.models import Paper

    workspace, _ = await _workspace_and_run(session)
    paper = Paper(title="Hand paper")
    session.add(paper)
    await session.flush()
    await workspaces.add_paper(session, workspace.id, paper.id)
    await branches.set_branch(session, workspace.id, paper_id=paper.id, state="go_further", directions=BOTH, reason=None)
    assert [i.paper_id for i in await snowball_next.snowball_next(session, workspace.id)] == [paper.id]

    await workspaces.remove_paper(session, workspace.id, paper.id)
    assert await snowball_next.snowball_next(session, workspace.id) == []
    out = await snowball_next.run_snowball_next(session, edge_providers, workspace.id)
    assert (out.new_hits, out.remaining) == (0, 0)

    await branches.set_branch(session, workspace.id, paper_id=paper.id, state=None, directions=[], reason=None)
    assert await session.scalar(select(WorkspaceBranchState).where(WorkspaceBranchState.paper_id == paper.id)) is None
