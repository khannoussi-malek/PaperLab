import uuid
from datetime import timedelta

import pytest

from app.core import screening
from app.models.references import ExternalRef
from app.models.workspace_search import WorkspaceSearchHit
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


async def test_a_hit_found_after_a_ranked_call_is_ranked_on_its_own_text(client, session):
    workspace, hits = await make_pool(session, [
        (POSITIVE, "relevant"), (NEGATIVE, "not_relevant"), ("sleep in adults", None),
    ])
    await client.get(_url(workspace))  # caches this pool's features
    ref = ExternalRef(title="late paper", abstract=POSITIVE)
    session.add(ref)
    await session.flush()
    late = WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=hits[0].run_id, external_ref_id=ref.id, source_method="database_search",
        normalized_title="late paper", first_seen_at=hits[2].first_seen_at + timedelta(seconds=1),
    )
    session.add(late)
    await session.flush()
    body = (await client.get(_url(workspace))).json()
    assert [item["id"] for item in body["items"]] == [str(late.id), str(hits[2].id)]


async def test_an_abstract_filled_after_a_ranked_call_counts(client, session):
    workspace, hits = await make_pool(session, [
        (POSITIVE, "relevant"), (NEGATIVE, "not_relevant"), ("sleep in adults", None), (None, None),
    ])
    await client.get(_url(workspace))  # caches the features while hit 3 has no abstract
    ref = await session.get(ExternalRef, hits[3].external_ref_id)
    ref.abstract = POSITIVE
    await session.flush()
    body = (await client.get(_url(workspace))).json()
    assert body["items"][0]["id"] == str(hits[3].id)


async def test_a_new_decision_reuses_the_cached_features(client, session, monkeypatch):
    workspace, hits = await make_pool(
        session, [(POSITIVE, "relevant"), (NEGATIVE, "not_relevant"), ("sleep in adults", None), ("graph", None)]
    )
    builds = []
    real = screening.features
    monkeypatch.setattr(screening, "features", lambda texts: builds.append(len(texts)) or real(texts))
    await client.get(_url(workspace))
    hits[2].stage1_status = "relevant"
    await session.flush()
    body = (await client.get(_url(workspace))).json()
    assert builds == [4]  # built once; the decision changed labels, not texts
    assert [item["id"] for item in body["items"]] == [str(hits[3].id)]


async def test_the_ranked_order_can_narrow_to_a_saved_searchs_new_finds(client, session):
    from datetime import datetime, timezone

    from app.core import saved_searches
    from app.models.workspace_search import WorkspaceSearchRun

    workspace, hits = await make_pool(session, [
        (POSITIVE, "relevant"), (NEGATIVE, "not_relevant"),
        ("graph neural network benchmark for molecules", None), ("sleep deprivation trial in older adults", None),
        ("sleep loss and memory in adults", None),
    ])
    looked = datetime(2026, 10, 1, tzinfo=timezone.utc)
    saved = await saved_searches.create(session, workspace.id, query="sleep", schedule="0 2 * * *", timezone="UTC",
                                        now=looked)
    run = WorkspaceSearchRun(workspace_id=workspace.id, query_text="sleep", filters_json={}, query_overrides_json={},
                             sources_json=["arxiv"], status="exhausted", started_at=looked, stats_json={},
                             saved_search_id=saved.id)
    session.add(run)
    await session.flush()
    for hit in (hits[2], hits[4]):  # the new finds: the graph paper and the sleep-loss paper
        hit.run_id, hit.first_seen_at = run.id, looked + timedelta(days=1)
    await session.commit()
    body = (await client.get(_url(workspace), params={
        "saved_search_id": str(saved.id), "found_after": looked.isoformat(),
    })).json()
    assert [item["id"] for item in body["items"]] == [str(hits[4].id), str(hits[2].id)]
    assert body["total_unscreened"] == 2


async def test_another_workspaces_saved_search_narrows_to_nothing(client, session):
    from app.core import saved_searches

    workspace, _ = await make_pool(session, [(POSITIVE, "relevant"), (NEGATIVE, "not_relevant"), ("x", None)])
    other, _ = await make_pool(session, [("y", None)])
    theirs = await saved_searches.create(session, other.id, query="q", schedule="0 2 * * *", timezone="UTC")
    resp = await client.get(_url(workspace), params={"saved_search_id": str(theirs.id)})
    assert resp.status_code == 200 and (resp.json()["items"], resp.json()["total_unscreened"]) == ([], 0)
