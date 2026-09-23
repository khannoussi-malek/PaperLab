import pytest

pytestmark = pytest.mark.anyio


async def test_start_run_over_http(client):
    ws = await client.post("/api/workspaces", json={"name": "Search API test"})
    workspace_id = ws.json()["id"]

    resp = await client.post(
        f"/api/workspaces/{workspace_id}/search/runs",
        json={"query": "bert", "filters": {}, "sources": ["arxiv"]},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "running"
    assert body["query_text"] == "bert"


async def test_start_run_enqueues_the_worker_job(client, arq):
    ws = await client.post("/api/workspaces", json={"name": "Enqueue test"})
    workspace_id = ws.json()["id"]

    resp = await client.post(
        f"/api/workspaces/{workspace_id}/search/runs",
        json={"query": "bert", "filters": {}, "sources": ["arxiv"]},
    )
    run_id = resp.json()["id"]

    assert arq.jobs == [("run_workspace_search", run_id)]


async def test_stop_and_get_run_over_http(client):
    ws = await client.post("/api/workspaces", json={"name": "Stop API test"})
    workspace_id = ws.json()["id"]
    started = await client.post(
        f"/api/workspaces/{workspace_id}/search/runs", json={"query": "bert", "filters": {}, "sources": ["arxiv"]}
    )
    run_id = started.json()["id"]

    stopped = await client.post(f"/api/workspaces/{workspace_id}/search/runs/{run_id}/stop")
    assert stopped.json()["status"] == "stopped"

    fetched = await client.get(f"/api/workspaces/{workspace_id}/search/runs/{run_id}")
    assert fetched.json()["status"] == "stopped"


async def test_restart_run_over_http(client, arq):
    ws = await client.post("/api/workspaces", json={"name": "Restart API test"})
    workspace_id = ws.json()["id"]
    started = await client.post(
        f"/api/workspaces/{workspace_id}/search/runs", json={"query": "bert", "filters": {}, "sources": ["arxiv"]}
    )
    run_id = started.json()["id"]
    await client.post(f"/api/workspaces/{workspace_id}/search/runs/{run_id}/stop")

    restarted = await client.post(f"/api/workspaces/{workspace_id}/search/runs/{run_id}")

    assert restarted.status_code == 200
    assert restarted.json()["status"] == "running"
    assert arq.jobs[-1] == ("run_workspace_search", run_id)


async def test_restart_a_running_run_is_409(client):
    ws = await client.post("/api/workspaces", json={"name": "Conflict API test"})
    workspace_id = ws.json()["id"]
    started = await client.post(
        f"/api/workspaces/{workspace_id}/search/runs", json={"query": "bert", "filters": {}, "sources": ["arxiv"]}
    )
    run_id = started.json()["id"]

    resp = await client.post(f"/api/workspaces/{workspace_id}/search/runs/{run_id}")

    assert resp.status_code == 409


async def test_get_unknown_run_is_404(client):
    ws = await client.post("/api/workspaces", json={"name": "404 test"})
    workspace_id = ws.json()["id"]
    resp = await client.get(f"/api/workspaces/{workspace_id}/search/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_start_run_for_unknown_workspace_is_404(client):
    resp = await client.post(
        "/api/workspaces/00000000-0000-0000-0000-000000000000/search/runs",
        json={"query": "bert", "filters": {}, "sources": ["arxiv"]},
    )
    assert resp.status_code == 404


async def test_get_run_for_wrong_workspace_is_404(client):
    owner_ws = await client.post("/api/workspaces", json={"name": "Owner workspace"})
    other_ws = await client.post("/api/workspaces", json={"name": "Other workspace"})
    started = await client.post(
        f"/api/workspaces/{owner_ws.json()['id']}/search/runs",
        json={"query": "bert", "filters": {}, "sources": ["arxiv"]},
    )
    run_id = started.json()["id"]

    resp = await client.get(f"/api/workspaces/{other_ws.json()['id']}/search/runs/{run_id}")

    assert resp.status_code == 404


async def test_stop_run_for_wrong_workspace_is_404(client):
    owner_ws = await client.post("/api/workspaces", json={"name": "Owner workspace"})
    other_ws = await client.post("/api/workspaces", json={"name": "Other workspace"})
    started = await client.post(
        f"/api/workspaces/{owner_ws.json()['id']}/search/runs",
        json={"query": "bert", "filters": {}, "sources": ["arxiv"]},
    )
    run_id = started.json()["id"]

    resp = await client.post(f"/api/workspaces/{other_ws.json()['id']}/search/runs/{run_id}/stop")

    assert resp.status_code == 404

    fetched = await client.get(f"/api/workspaces/{owner_ws.json()['id']}/search/runs/{run_id}")
    assert fetched.json()["status"] == "running"


async def test_list_hits_paginates_by_cursor(session, client):
    import uuid as uuid_mod
    from datetime import datetime, timezone

    from app.models.workspace import Workspace
    from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

    workspace = Workspace(name=f"Hit list {uuid_mod.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", filters_json={}, query_overrides_json={},
        sources_json=[], status="exhausted", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    for i in range(5):
        session.add(WorkspaceSearchHit(
            workspace_id=workspace.id, run_id=run.id, source_method="database_search",
            normalized_title=f"paper {i}", first_seen_at=datetime.now(timezone.utc),
        ))
    await session.commit()

    first_page = await client.get(f"/api/workspaces/{workspace.id}/search/hits?limit=2")
    assert len(first_page.json()["items"]) == 2
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None

    second_page = await client.get(f"/api/workspaces/{workspace.id}/search/hits?limit=2&after={cursor}")
    assert len(second_page.json()["items"]) == 2
    first_ids = {h["id"] for h in first_page.json()["items"]}
    second_ids = {h["id"] for h in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)

    # Walk the cursor to exhaustion: every hit must appear exactly once across all pages, confirming the
    # keyset cursor produces no gaps and no overlap end to end, not just between the first two pages.
    seen_ids = [*first_ids, *second_ids]
    next_cursor = second_page.json()["next_cursor"]
    while next_cursor is not None:
        page = await client.get(f"/api/workspaces/{workspace.id}/search/hits?limit=2&after={next_cursor}")
        body = page.json()
        seen_ids.extend(h["id"] for h in body["items"])
        next_cursor = body["next_cursor"]

    assert len(seen_ids) == 5
    assert len(set(seen_ids)) == 5


async def test_list_hits_filters_by_stage1_status(session, client):
    import uuid as uuid_mod
    from datetime import datetime, timezone

    from app.models.workspace import Workspace
    from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

    workspace = Workspace(name=f"Hit filter {uuid_mod.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", filters_json={}, query_overrides_json={},
        sources_json=[], status="exhausted", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    session.add(WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, source_method="database_search",
        normalized_title="relevant one", stage1_status="relevant", first_seen_at=datetime.now(timezone.utc),
    ))
    session.add(WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, source_method="database_search",
        normalized_title="excluded one", stage1_status="not_relevant", first_seen_at=datetime.now(timezone.utc),
    ))
    await session.commit()

    resp = await client.get(f"/api/workspaces/{workspace.id}/search/hits?stage1_status=relevant")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["normalized_title"] == "relevant one"


async def test_list_hits_with_zero_limit_is_422(client):
    ws = await client.post("/api/workspaces", json={"name": "Zero limit test"})
    workspace_id = ws.json()["id"]

    resp = await client.get(f"/api/workspaces/{workspace_id}/search/hits?limit=0")

    assert resp.status_code == 422


async def test_list_hits_with_malformed_cursor_is_422(client):
    ws = await client.post("/api/workspaces", json={"name": "Bad cursor test"})
    workspace_id = ws.json()["id"]

    resp = await client.get(f"/api/workspaces/{workspace_id}/search/hits?after=not-valid-base64-json")

    assert resp.status_code == 422


async def _make_hit(session, title: str, workspace_id=None):
    import uuid as uuid_mod
    from datetime import datetime, timezone

    from app.models.workspace import Workspace
    from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

    if workspace_id is None:
        workspace = Workspace(name=f"Patch {uuid_mod.uuid4().hex[:8]}")
        session.add(workspace)
        await session.flush()
        workspace_id = workspace.id
    run = WorkspaceSearchRun(
        workspace_id=workspace_id, query_text="q", filters_json={}, query_overrides_json={},
        sources_json=[], status="exhausted", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=workspace_id, run_id=run.id, source_method="database_search",
        normalized_title=title, first_seen_at=datetime.now(timezone.utc),
    )
    session.add(hit)
    await session.commit()
    return hit.id


async def test_patch_hit_sets_stage1_fields(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "patch target")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_id)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}",
        json={"stage1_status": "relevant", "priority": 4, "topic_fit": "same_topic"},
    )

    assert resp.status_code == 200
    assert resp.json()["stage1_status"] == "relevant"
    assert resp.json()["priority"] == 4


async def test_patch_hit_exclude_requires_a_reason(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "exclude target")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_id)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}", json={"stage1_status": "not_relevant"}
    )

    assert resp.status_code == 422


async def test_patch_hit_exclude_with_a_reason_succeeds(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "exclude target 2")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_id)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}",
        json={"stage1_status": "not_relevant", "stage1_exclude_reason": "wrong_topic"},
    )

    assert resp.status_code == 200
    assert resp.json()["stage1_status"] == "not_relevant"
    assert resp.json()["stage1_exclude_reason"] == "wrong_topic"


async def test_patch_hit_cannot_null_out_reason_while_still_not_relevant(session, client):
    """A second PATCH that omits stage1_status entirely must not be able to null the reason out from under an
    already-not_relevant hit — the schema validator alone can't catch this since it never sees the hit's
    persisted state, only this request's own fields."""
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "reason bypass target")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_id)).workspace_id

    first = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}",
        json={"stage1_status": "not_relevant", "stage1_exclude_reason": "wrong_topic"},
    )
    assert first.status_code == 200

    second = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}",
        json={"stage1_exclude_reason": None},
    )

    assert second.status_code == 422
    hit = await session.get(WorkspaceSearchHit, hit_id)
    assert hit.stage1_status == "not_relevant"
    assert hit.stage1_exclude_reason == "wrong_topic"


async def test_patch_hit_rejects_a_garbage_stage1_status(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "garbage status")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_id)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}", json={"stage1_status": "super_relevant"}
    )

    assert resp.status_code == 422


async def test_patch_hit_rejects_priority_out_of_range(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "bad priority")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_id)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/{hit_id}", json={"priority": 9}
    )

    assert resp.status_code == 422


async def test_patch_hit_for_unknown_hit_is_404(client):
    ws = await client.post("/api/workspaces", json={"name": "Patch 404 test"})
    workspace_id = ws.json()["id"]

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/00000000-0000-0000-0000-000000000000",
        json={"stage1_status": "relevant"},
    )

    assert resp.status_code == 404


async def test_patch_hit_for_wrong_workspace_is_404(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_id = await _make_hit(session, "wrong workspace target")
    other_ws = await client.post("/api/workspaces", json={"name": "Other patch workspace"})
    other_workspace_id = other_ws.json()["id"]

    resp = await client.patch(
        f"/api/workspaces/{other_workspace_id}/search/hits/{hit_id}", json={"stage1_status": "relevant"}
    )

    assert resp.status_code == 404
    hit = await session.get(WorkspaceSearchHit, hit_id)
    assert hit.stage1_status is None


async def test_bulk_patch_hits(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    hit_a = await _make_hit(session, "bulk a")
    workspace_id = (await session.get(WorkspaceSearchHit, hit_a)).workspace_id
    hit_b = await _make_hit(session, "bulk b", workspace_id=workspace_id)

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/bulk",
        json={"hit_ids": [str(hit_a), str(hit_b)], "stage1_status": "relevant"},
    )

    assert resp.status_code == 200
    assert resp.json()["updated"] == 2


async def test_bulk_patch_hits_exclude_requires_a_reason(session, client):
    hit_a = await _make_hit(session, "bulk exclude a")
    from app.models.workspace_search import WorkspaceSearchHit

    workspace_id = (await session.get(WorkspaceSearchHit, hit_a)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/bulk",
        json={"hit_ids": [str(hit_a)], "stage1_status": "not_relevant"},
    )

    assert resp.status_code == 422


async def test_bulk_patch_hits_rejects_a_garbage_stage1_status(session, client):
    hit_a = await _make_hit(session, "bulk garbage a")
    from app.models.workspace_search import WorkspaceSearchHit

    workspace_id = (await session.get(WorkspaceSearchHit, hit_a)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/bulk",
        json={"hit_ids": [str(hit_a)], "stage1_status": "super_relevant"},
    )

    assert resp.status_code == 422


async def test_bulk_patch_hits_only_updates_hits_in_the_workspace(session, client):
    from app.models.workspace_search import WorkspaceSearchHit

    owned_hit = await _make_hit(session, "owned bulk hit")
    other_hit = await _make_hit(session, "other workspace bulk hit")
    workspace_id = (await session.get(WorkspaceSearchHit, owned_hit)).workspace_id

    resp = await client.patch(
        f"/api/workspaces/{workspace_id}/search/hits/bulk",
        json={"hit_ids": [str(owned_hit), str(other_hit)], "stage1_status": "relevant"},
    )

    assert resp.status_code == 200
    assert resp.json()["updated"] == 1
    other = await session.get(WorkspaceSearchHit, other_hit)
    assert other.stage1_status is None
