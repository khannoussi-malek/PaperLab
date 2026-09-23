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
