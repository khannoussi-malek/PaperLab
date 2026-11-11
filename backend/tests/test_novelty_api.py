import uuid

import pytest

from app.core import novelty
from app.core.errors import Conflict

pytestmark = pytest.mark.anyio


async def test_returns_the_report(client, monkeypatch):
    pid, cid = uuid.uuid4(), uuid.uuid4()

    async def fake(session, text, workspace=None, *, embedder=None):
        assert (text, workspace) == ("my idea", None)
        paper = novelty.NoveltyPaper(pid, "T", 2021, "related", 0.3, "quote", 4, "Intro", False, cid)
        return novelty.NoveltyReport([paper], 5, "note")

    monkeypatch.setattr(novelty, "check", fake)
    response = await client.post("/api/novelty", json={"text": "my idea"})
    assert response.status_code == 200
    body = response.json()
    assert body["note"] == "note" and body["searched_papers"] == 5
    assert body["papers"][0] | {"paper_id": None, "chunk_id": None} == {
        "paper_id": None, "chunk_id": None, "title": "T", "year": 2021, "label": "related", "distance": 0.3,
        "passage": "quote", "page": 4, "section": "Intro", "from_abstract": False,
    }


async def test_text_is_required(client):
    assert (await client.post("/api/novelty", json={})).status_code == 422


async def test_empty_text_and_unknown_workspace_use_the_usual_error_statuses(client):
    assert (await client.post("/api/novelty", json={"text": "  "})).status_code == 422
    missing = await client.post("/api/novelty", json={"text": "idea", "workspace": "No such workspace"})
    assert missing.status_code == 404


async def test_text_too_long_is_422_with_its_code(client):
    response = await client.post("/api/novelty", json={"text": "x" * (novelty.MAX_CHARS + 1)})
    assert response.status_code == 422 and "text_too_long" in response.text


async def test_search_not_set_up_is_409(client, monkeypatch):
    async def refuse(session, text, workspace=None, *, embedder=None):
        raise Conflict("search_not_set_up")

    monkeypatch.setattr(novelty, "check", refuse)
    assert (await client.post("/api/novelty", json={"text": "idea"})).status_code == 409
