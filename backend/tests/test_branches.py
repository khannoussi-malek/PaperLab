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
