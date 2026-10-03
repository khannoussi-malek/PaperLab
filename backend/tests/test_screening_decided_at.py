import pytest

from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio


async def test_single_review_sets_decided_at(client, session):
    workspace, [hit] = await make_pool(session, [("sleep", None)])
    resp = await client.patch(
        f"/api/workspaces/{workspace.id}/search/hits/{hit.id}", json={"stage1_status": "relevant"}
    )
    assert resp.status_code == 200
    await session.refresh(hit)
    assert hit.stage1_decided_at is not None


async def test_clearing_a_decision_clears_decided_at(client, session):
    workspace, [hit] = await make_pool(session, [("sleep", "relevant")])
    resp = await client.patch(f"/api/workspaces/{workspace.id}/search/hits/{hit.id}", json={"stage1_status": None})
    assert resp.status_code == 200
    await session.refresh(hit)
    assert (hit.stage1_status, hit.stage1_decided_at) == (None, None)


async def test_a_note_only_patch_leaves_decided_at_alone(client, session):
    workspace, [hit] = await make_pool(session, [("sleep", "relevant")])
    before = hit.stage1_decided_at
    await client.patch(f"/api/workspaces/{workspace.id}/search/hits/{hit.id}", json={"stage1_note": "check"})
    await session.refresh(hit)
    assert hit.stage1_decided_at == before


async def test_bulk_review_sets_decided_at(client, session):
    workspace, hits = await make_pool(session, [("a", None), ("b", None)])
    resp = await client.patch(
        f"/api/workspaces/{workspace.id}/search/hits/bulk",
        json={"hit_ids": [str(h.id) for h in hits], "stage1_status": "not_relevant", "stage1_exclude_reason": "other"},
    )
    assert resp.json() == {"updated": 2}
    for hit in hits:
        await session.refresh(hit)
        assert hit.stage1_decided_at is not None
