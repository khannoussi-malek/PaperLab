import uuid

import pytest

from app.core import notes
from app.models import Paper

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database


async def make_paper(session, title="Workspace paper") -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", page_count=2)
    session.add(paper)
    await session.commit()
    return paper


async def test_workspace_lifecycle_over_http(client):
    created = await client.post("/api/workspaces", json={"name": f"  Thesis ch.2 {RUN} "})
    assert created.status_code == 201
    workspace = created.json()
    assert (workspace["name"], workspace["paper_count"], workspace["note_count"]) == (f"Thesis ch.2 {RUN}", 0, 0)
    assert {"id", "created_at"} <= workspace.keys()

    listed = (await client.get("/api/workspaces")).json()
    assert workspace in listed

    renamed = await client.patch(f"/api/workspaces/{workspace['id']}", json={"name": f"Thesis ch.3 {RUN}"})
    assert (renamed.status_code, renamed.json()["name"]) == (200, f"Thesis ch.3 {RUN}")

    assert (await client.delete(f"/api/workspaces/{workspace['id']}")).status_code == 204
    assert workspace["id"] not in [w["id"] for w in (await client.get("/api/workspaces")).json()]


async def test_membership_papers_and_notes_over_http(client, session):
    workspace = (await client.post("/api/workspaces", json={"name": f"Thesis {RUN}"})).json()
    paper = await make_paper(session)
    note = await notes.create_human_note(
        session, "key claim", notes.Anchor(paper_id=paper.id, page=1, bbox=[(1, 2, 3, 4)], quoted_text="a quote")
    )
    member = f"/api/workspaces/{workspace['id']}/papers/{paper.id}"

    assert [(await client.put(member)).status_code for _ in range(2)] == [204, 204]

    papers = (await client.get(f"/api/workspaces/{workspace['id']}/papers")).json()
    assert [(p["id"], p["workspace_ids"]) for p in papers] == [(str(paper.id), [workspace["id"]])]
    assert (await client.get(f"/api/papers/{paper.id}")).json()["workspace_ids"] == [workspace["id"]]
    listed_notes = (await client.get(f"/api/workspaces/{workspace['id']}/notes")).json()
    assert [(n["id"], n["body"], n["provenance"]) for n in listed_notes] == [(str(note.id), "key claim", "human")]
    counted = next(w for w in (await client.get("/api/workspaces")).json() if w["id"] == workspace["id"])
    assert (counted["paper_count"], counted["note_count"]) == (1, 1)

    assert [(await client.delete(member)).status_code for _ in range(2)] == [204, 204]
    assert (await client.get(f"/api/workspaces/{workspace['id']}/papers")).json() == []


async def test_workspace_http_errors(client, session):
    first = (await client.post("/api/workspaces", json={"name": f"Thesis {RUN}"})).json()
    second = (await client.post("/api/workspaces", json={"name": f"Review {RUN}"})).json()
    paper = await make_paper(session)
    missing = uuid.uuid4()
    not_found = {"detail": f"workspace {missing} not found"}
    no_paper = {"detail": f"paper {missing} not found"}
    taken = {"detail": "workspace_name_taken"}
    bad_name = {"detail": "a workspace name needs 1 to 80 characters"}

    cases = [
        ("post", "/api/workspaces", {"name": f"Thesis {RUN}"}, 409, taken),
        ("post", "/api/workspaces", {"name": "   "}, 422, bad_name),
        ("post", "/api/workspaces", {"name": "x" * 81}, 422, bad_name),
        ("post", "/api/workspaces", {}, 422, None),
        ("patch", f"/api/workspaces/{second['id']}", {"name": f"Thesis {RUN}"}, 409, taken),
        ("patch", f"/api/workspaces/{first['id']}", {"name": ""}, 422, bad_name),
        ("patch", f"/api/workspaces/{missing}", {"name": "New"}, 404, not_found),
        ("delete", f"/api/workspaces/{missing}", None, 404, not_found),
        ("put", f"/api/workspaces/{missing}/papers/{paper.id}", None, 404, not_found),
        ("put", f"/api/workspaces/{first['id']}/papers/{missing}", None, 404, no_paper),
        ("delete", f"/api/workspaces/{missing}/papers/{paper.id}", None, 404, not_found),
        ("delete", f"/api/workspaces/{first['id']}/papers/{missing}", None, 404, no_paper),
        ("get", f"/api/workspaces/{missing}/papers", None, 404, not_found),
        ("get", f"/api/workspaces/{missing}/notes", None, 404, not_found),
        ("get", "/api/workspaces/not-a-uuid/notes", None, 422, None),
    ]
    for method, path, body, status, detail in cases:
        response = await client.request(method, path, json=body)
        assert response.status_code == status, (method, path, response.text)
        if detail is not None:
            assert response.json() == detail


async def test_upload_into_a_workspace(client, arq, pdf_dir):
    workspace = (await client.post("/api/workspaces", json={"name": f"Thesis {RUN}"})).json()
    pdf = {"file": ("paper.pdf", b"%PDF-1.7\nbody", "application/pdf")}

    uploaded = await client.post("/api/papers", files=pdf, data={"workspace_id": workspace["id"]})
    plain = await client.post("/api/papers", files=pdf)
    missing = uuid.uuid4()
    unknown = await client.post("/api/papers", files=pdf, data={"workspace_id": str(missing)})

    assert (uploaded.status_code, uploaded.json()["workspace_ids"]) == (201, [workspace["id"]])
    assert (plain.status_code, plain.json()["workspace_ids"]) == (201, [])
    assert (unknown.status_code, unknown.json()) == (404, {"detail": f"workspace {missing} not found"})
    # The unknown workspace is refused before anything is stored.
    assert arq.jobs == [("ingest_paper", uploaded.json()["id"]), ("ingest_paper", plain.json()["id"])]
    assert len(list(pdf_dir.iterdir())) == 2
    papers = (await client.get(f"/api/workspaces/{workspace['id']}/papers")).json()
    assert [p["id"] for p in papers] == [uploaded.json()["id"]]
