import uuid

import pytest

from app.core import manuscripts, queue

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
FINDING_KEYS = {"check", "severity", "file", "line", "message", "fix_hint"}


@pytest.fixture(autouse=True)
def wiring(arq, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)


async def made(client, session):
    mid = (await client.post("/api/manuscripts", json={"title": "D", "template": "article"})).json()["id"]
    await manuscripts.upsert_text(session, uuid.UUID(mid), "main.tex", "Hi.\nSee \\cite{nowhere}.\n")
    return mid


async def test_list_checks(client, session):
    mid = await made(client, session)
    body = (await client.get(f"/api/manuscripts/{mid}/checks")).json()
    assert body[0] == {"name": "citations.missing_keys", "cost": "cheap",
                       "description": "Cited keys that match no paper or .bib entry"}


async def test_run_all_returns_findings_counts_and_ran(client, session):
    mid = await made(client, session)
    r = await client.post(f"/api/manuscripts/{mid}/checks/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert "citations.missing_keys" in body["ran"] and set(body["counts"]) == {"error", "warning", "info"}
    hit = next(f for f in body["findings"] if "nowhere" in f["message"])
    assert set(hit) == FINDING_KEYS and (hit["file"], hit["line"], hit["severity"]) == ("main.tex", 2, "error")
    assert body["counts"]["error"] >= 1


async def test_names_and_cost_narrow_the_run(client, session):
    mid = await made(client, session)
    url = f"/api/manuscripts/{mid}/checks/run"
    assert (await client.post(url, json={"names": ["citations.missing_keys"]})).json()["ran"] == ["citations.missing_keys"]
    assert (await client.post(url, json={"cost": "cheap"})).json()["ran"] == ["citations.missing_keys"]


async def test_errors(client, session):
    mid = await made(client, session)
    url = f"/api/manuscripts/{mid}/checks/run"
    assert (await client.post(url, json={"names": ["nope"]})).status_code == 422
    assert (await client.post(url, json={"extra": 1})).status_code == 422
    assert (await client.post(url, json={"names": []})).status_code == 422
    assert (await client.post(url, json={"cost": "huge"})).status_code == 422
    ghost = uuid.uuid4()
    assert (await client.post(f"/api/manuscripts/{ghost}/checks/run", json={})).status_code == 404
    assert (await client.get(f"/api/manuscripts/{ghost}/checks")).status_code == 404
