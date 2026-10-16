import uuid

import pytest

from app.core import workspaces
from app.models import Paper

pytestmark = pytest.mark.anyio


async def _paper(session, ws, title):
    paper = Paper(title=title, file_path="/nonexistent.pdf", page_count=5, doi=f"10.5555/{uuid.uuid4().hex}")
    session.add(paper)
    await session.commit()
    await workspaces.add_paper(session, ws, paper.id)
    return paper


async def _ws(session, name):
    return (await workspaces.create(session, name)).id


async def _apply(client, ws, tag, papers):
    return await client.post(
        f"/api/workspaces/{ws}/tags/apply", json={"tag": tag, "paper_ids": [str(p.id) for p in papers]}
    )


async def test_apply_list_and_paper_tag_map(client, session):
    ws = await _ws(session, "Tags API a")
    a, b = await _paper(session, ws, "A"), await _paper(session, ws, "B")

    resp = await _apply(client, ws, "Zeta", [a, b])
    assert resp.status_code == 200
    assert resp.json() == {"tag": "Zeta", "changed": 2, "unchanged": 0, "skipped": []}
    await _apply(client, ws, "alpha", [a])

    listed = (await client.get(f"/api/workspaces/{ws}/tags")).json()
    assert [(t["name"], t["papers"]) for t in listed] == [("alpha", 1), ("Zeta", 2)]
    assert {"peer_reviewed", "preprint", "unknown_review", "full_text", "abstract", "metadata"} <= listed[0].keys()

    mapping = (await client.get(f"/api/workspaces/{ws}/paper-tags")).json()
    assert mapping == {str(a.id): ["alpha", "Zeta"], str(b.id): ["Zeta"]}


async def test_remove(client, session):
    ws = await _ws(session, "Tags API b")
    a = await _paper(session, ws, "A")
    await _apply(client, ws, "x", [a])

    resp = await client.post(f"/api/workspaces/{ws}/tags/remove", json={"tag": "x", "paper_ids": [str(a.id)]})

    assert resp.json()["changed"] == 1
    assert (await client.get(f"/api/workspaces/{ws}/paper-tags")).json() == {}


async def _tag_id(client, ws, name):
    return next(t["id"] for t in (await client.get(f"/api/workspaces/{ws}/tags")).json() if t["name"] == name)


async def test_rename_and_clash(client, session):
    ws = await _ws(session, "Tags API c")
    a = await _paper(session, ws, "A")
    await _apply(client, ws, "RQ1/RQ2 %x", [a])
    await _apply(client, ws, "two", [a])

    ok = await client.patch(
        f"/api/workspaces/{ws}/tags/{await _tag_id(client, ws, 'RQ1/RQ2 %x')}", json={"new_name": "uno"}
    )
    assert ok.status_code == 200
    assert ok.json() == {"old": "RQ1/RQ2 %x", "new": "uno"}

    clash = await client.patch(
        f"/api/workspaces/{ws}/tags/{await _tag_id(client, ws, 'uno')}", json={"new_name": "TWO"}
    )
    assert clash.status_code == 409
    assert clash.json()["detail"] == "tag_exists"


async def test_delete_keeps_papers_and_handles_odd_names(client, session):
    ws = await _ws(session, "Tags API d")
    a = await _paper(session, ws, "A")
    await _apply(client, ws, "RQ1/RQ2 %x", [a])

    resp = await client.delete(f"/api/workspaces/{ws}/tags/{await _tag_id(client, ws, 'RQ1/RQ2 %x')}")

    assert resp.json() == {"tag": "RQ1/RQ2 %x", "papers": 1}
    assert len((await client.get(f"/api/workspaces/{ws}/papers")).json()) == 1
    assert (await client.get(f"/api/workspaces/{ws}/tags")).json() == []


async def test_foreign_tag_id_is_404(client, session):
    w1, w2 = await _ws(session, "Tags API g1"), await _ws(session, "Tags API g2")
    a = await _paper(session, w1, "A")
    await _apply(client, w1, "mine", [a])
    tag_id = await _tag_id(client, w1, "mine")

    assert (await client.patch(f"/api/workspaces/{w2}/tags/{tag_id}", json={"new_name": "x"})).status_code == 404
    assert (await client.delete(f"/api/workspaces/{w2}/tags/{tag_id}")).status_code == 404
    assert (await client.delete(f"/api/workspaces/{w1}/tags/{uuid.uuid4()}")).status_code == 404


async def test_paper_tags_grouped_per_workspace(client, session):
    w1, w2, w3 = [await _ws(session, f"Tags API e{i}") for i in range(3)]
    p = await _paper(session, w1, "P")
    await workspaces.add_paper(session, w2, p.id)
    await workspaces.add_paper(session, w3, p.id)
    await _apply(client, w1, "b", [p])
    await _apply(client, w1, "A", [p])
    await _apply(client, w2, "z", [p])

    groups = (await client.get(f"/api/papers/{p.id}/tags")).json()

    by_ws = {g["workspace_id"]: g for g in groups}
    assert set(by_ws) == {str(w1), str(w2)}
    assert by_ws[str(w1)]["tags"] == ["A", "b"]
    assert by_ws[str(w1)]["workspace_name"] == "Tags API e0"


async def test_not_found_and_invalid(client, session):
    missing = uuid.uuid4()
    assert (await client.get(f"/api/workspaces/{missing}/tags")).status_code == 404
    assert (await client.get(f"/api/workspaces/{missing}/paper-tags")).status_code == 404
    assert (await client.get(f"/api/papers/{missing}/tags")).status_code == 404

    ws = await _ws(session, "Tags API f")
    a = await _paper(session, ws, "A")
    bad = await _apply(client, ws, "   ", [a])
    assert bad.status_code == 422
    assert bad.json()["detail"] == "invalid_tag_name"
