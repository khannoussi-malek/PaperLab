"""POST/PATCH/DELETE /api/links: the owner's own links (P6)."""

import uuid

import pytest

from app.core import paper_links
from app.models import Paper

pytestmark = pytest.mark.anyio


async def add_papers(session, count: int = 2) -> list[Paper]:
    papers = [Paper(title=f"Links API {n} {uuid.uuid4().hex[:8]}", file_path="/nonexistent.pdf") for n in range(count)]
    session.add_all(papers)
    await session.commit()
    return papers


async def test_create_returns_201_and_the_link(session, client):
    left, right = await add_papers(session)

    response = await client.post(
        "/api/links", json={"from_paper": str(left.id), "to_paper": str(right.id), "label": " builds on "}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["from_paper"] == str(left.id) and body["to_paper"] == str(right.id) and body["label"] == "builds on"
    assert uuid.UUID(body["id"])


async def test_every_refusal_carries_its_status_and_message(session, client):
    left, right = await add_papers(session)
    await paper_links.create(session, left.id, right.id, "builds on")

    unknown = await client.post(
        "/api/links", json={"from_paper": str(left.id), "to_paper": str(uuid.uuid4()), "label": "builds on"}
    )
    duplicate = await client.post(
        "/api/links", json={"from_paper": str(right.id), "to_paper": str(left.id), "label": "builds on"}
    )
    itself = await client.post(
        "/api/links", json={"from_paper": str(left.id), "to_paper": str(left.id), "label": "builds on"}
    )
    blank = await client.post(
        "/api/links", json={"from_paper": str(left.id), "to_paper": str(right.id), "label": "   "}
    )
    long = await client.post(
        "/api/links", json={"from_paper": str(left.id), "to_paper": str(right.id), "label": "x" * 81}
    )

    assert unknown.status_code == 404
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == paper_links.ALREADY_LINKED
    assert itself.status_code == 422
    assert blank.status_code == 422
    assert blank.json()["detail"] == paper_links.EMPTY_LABEL
    assert long.status_code == 422
    assert long.json()["detail"] == paper_links.LABEL_TOO_LONG


async def test_patch_changes_only_the_label_and_delete_returns_204(session, client):
    left, right = await add_papers(session)
    link = await paper_links.create(session, left.id, right.id, "builds on")

    patched = await client.patch(f"/api/links/{link.id}", json={"label": " contradicts "})
    assert patched.status_code == 200
    assert patched.json() == {
        "id": str(link.id),
        "from_paper": str(left.id),
        "to_paper": str(right.id),
        "label": "contradicts",
    }

    assert (await client.patch(f"/api/links/{link.id}", json={"label": "  "})).status_code == 422
    assert (await client.delete(f"/api/links/{link.id}")).status_code == 204
    assert (await client.delete(f"/api/links/{link.id}")).status_code == 404
    assert (await client.patch(f"/api/links/{link.id}", json={"label": "gone"})).status_code == 404
