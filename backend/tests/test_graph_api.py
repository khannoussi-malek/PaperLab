"""GET /api/graph: the graph page's one request (D109)."""

import uuid

import pytest

from app.core import paper_links, workspaces
from app.models import Chunk, Paper
from tests.conftest import unit_vector

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]


async def add_papers(session, *titles: str) -> list[Paper]:
    papers = [Paper(title=title, file_path="/nonexistent.pdf", year=2020, status="ready") for title in titles]
    session.add_all(papers)
    await session.commit()
    return papers


async def test_the_payload_carries_every_paper_its_links_and_no_vectors(session, client):
    left, right = await add_papers(session, f"API left {RUN}", f"API right {RUN}")
    workspace = await workspaces.create(session, f"API {RUN}")
    for paper in (left, right):
        await workspaces.add_paper(session, workspace.id, paper.id)
    session.add(
        Chunk(
            paper_id=left.id,
            ordinal=0,
            page=1,
            bbox=[[0, 0, 1, 1]],
            text="body",
            embedding=unit_vector(f"{RUN}-left"),
            embed_model="test",
            strategy_ver=1,
        )
    )
    await session.commit()

    response = await client.get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is False
    node = next(n for n in body["nodes"] if n["id"] == str(left.id))
    assert node == {
        "id": str(left.id),
        "title": left.title,
        "year": 2020,
        "workspaces": [f"API {RUN}"],
        "has_notes": False,
        "status": "ready",
    }
    ours = [
        link
        for link in body["links"]
        if {link["source"], link["target"]} == {str(left.id), str(right.id)}
    ]
    assert [link["kind"] for link in ours] == ["same_workspace"]
    assert ours[0]["id"] is None and ours[0]["label"] is None
    assert "embedding" not in response.text and "vector" not in response.text


async def test_a_manual_link_carries_its_id_and_label(session, client):
    left, right = await add_papers(session, f"Drawn from {RUN}", f"Drawn to {RUN}")
    link = await paper_links.create(session, left.id, right.id, "builds on")

    body = (await client.get("/api/graph")).json()

    drawn = next(item for item in body["links"] if item["kind"] == "manual" and item["id"] == str(link.id))
    assert drawn == {
        "source": str(left.id),
        "target": str(right.id),
        "kind": "manual",
        "id": str(link.id),
        "label": "builds on",
    }


async def test_a_workspace_narrows_the_payload_and_an_unknown_one_is_404(session, client):
    inside, outside = await add_papers(session, f"WS in {RUN}", f"WS out {RUN}")
    workspace = await workspaces.create(session, f"WS {RUN}")
    await workspaces.add_paper(session, workspace.id, inside.id)

    body = (await client.get(f"/api/graph?workspace={workspace.id}")).json()

    assert [node["title"] for node in body["nodes"]] == [inside.title]
    assert (await client.get(f"/api/graph?workspace={uuid.uuid4()}")).status_code == 404
