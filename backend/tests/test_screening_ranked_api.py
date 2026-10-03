import uuid

import pytest

from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio

POSITIVE = "randomised controlled trial of sleep deprivation in adults"
NEGATIVE = "a survey of graph neural networks for molecules"


def _url(workspace):
    return f"/api/workspaces/{workspace.id}/search/hits/ranked"


async def test_ranked_hits_put_likely_relevant_first(client, session):
    workspace, hits = await make_pool(session, [
        (POSITIVE, "relevant"), (NEGATIVE, "not_relevant"),
        ("graph neural network benchmark for molecules", None), ("sleep deprivation trial in older adults", None),
    ])
    body = (await client.get(_url(workspace))).json()
    assert [item["id"] for item in body["items"]] == [str(hits[3].id), str(hits[2].id)]
    assert (body["trained"], body["total_unscreened"]) == (True, 2)
    assert body["items"][0]["abstract"] == "sleep deprivation trial in older adults"


async def test_cold_start_keeps_found_order_and_leaves_the_flag_off(client, session):
    workspace, hits = await make_pool(session, [(POSITIVE, "relevant"), ("b", None), ("a", None)])
    body = (await client.get(_url(workspace))).json()
    assert body["trained"] is False
    assert [item["id"] for item in body["items"]] == [str(hits[1].id), str(hits[2].id)]
    await session.refresh(workspace)
    assert workspace.screening_ranked_used is False


async def test_a_trained_order_marks_the_workspace_for_prisma(client, session):
    workspace, _ = await make_pool(session, [(POSITIVE, "relevant"), (NEGATIVE, "not_relevant"), ("x", None)])
    await client.get(_url(workspace))
    await session.refresh(workspace)
    assert workspace.screening_ranked_used is True


async def test_limit_caps_items_but_not_the_total(client, session):
    workspace, _ = await make_pool(session, [(POSITIVE, "relevant"), (NEGATIVE, "not_relevant")] + [("x", None)] * 3)
    body = (await client.get(_url(workspace), params={"limit": 2})).json()
    assert (len(body["items"]), body["total_unscreened"]) == (2, 3)


@pytest.mark.parametrize("limit", [0, 501])
async def test_limit_out_of_range_is_422(client, session, limit):
    workspace, _ = await make_pool(session, [])
    assert (await client.get(_url(workspace), params={"limit": limit})).status_code == 422


async def test_other_workspaces_hits_never_show(client, session):
    workspace, _ = await make_pool(session, [("mine", None)])
    await make_pool(session, [("theirs", None)])
    body = (await client.get(_url(workspace))).json()
    assert [item["abstract"] for item in body["items"]] == ["mine"]


async def test_unknown_workspace_is_404(client):
    assert (await client.get(f"/api/workspaces/{uuid.uuid4()}/search/hits/ranked")).status_code == 404


async def test_stop_hint_after_fifty_not_relevant_in_a_row(client, session):
    rows = [(POSITIVE, "relevant")] + [(NEGATIVE, "not_relevant")] * 50 + [("x", None)]
    workspace, _ = await make_pool(session, rows)
    body = (await client.get(_url(workspace))).json()
    assert (body["streak"], body["threshold"], body["show_stop_hint"]) == (50, 50, True)


async def test_ranked_hit_without_external_ref_uses_normalized_title(client, session):
    workspace, hits = await make_pool(session, [(POSITIVE, "relevant"), (NEGATIVE, "not_relevant"), ("", None)])
    hits[2].external_ref_id = None
    hits[2].normalized_title = "sleep deprivation trial"
    await session.flush()
    body = (await client.get(_url(workspace))).json()
    assert body["items"][0]["id"] == str(hits[2].id)
    assert body["items"][0]["title"] is None
