import uuid

import pytest
from test_note_papers import paper_only_note

from app.models import Paper

pytestmark = pytest.mark.anyio


async def make_paper(session, file_path: str, page_count=2) -> Paper:
    paper = Paper(title="api paper", file_path=file_path, page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


async def test_note_lifecycle_over_http(client, session, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    paper = await make_paper(session, str(pdf))

    pdf_response = await client.get(f"/api/papers/{paper.id}/file")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"

    anchor = {"paper_id": str(paper.id), "page": 2, "bbox": [[10, 20, 30, 40]], "quoted_text": "self-atten-\ntion"}
    created = await client.post("/api/notes", json={"body": "key claim", "anchor": anchor})
    assert created.status_code == 201
    note = created.json()
    assert note["provenance"] == "human"
    assert note["anchors"] == [
        {"paper_id": str(paper.id), "page": 2, "bbox": [[10, 20, 30, 40]], "quoted_text": "self-attention"}
    ]

    listed = await client.get(f"/api/papers/{paper.id}/notes")
    assert [n["id"] for n in listed.json()] == [note["id"]]

    patched = await client.patch(f"/api/notes/{note['id']}", json={"body": "revised"})
    assert patched.status_code == 200
    assert patched.json()["body"] == "revised"

    assert (await client.delete(f"/api/notes/{note['id']}")).status_code == 204
    assert (await client.get(f"/api/papers/{paper.id}/notes")).json() == []

    assert (await client.delete(f"/api/papers/{paper.id}")).status_code == 204
    assert (await client.get(f"/api/papers/{paper.id}")).status_code == 404
    assert not pdf.exists()


async def test_note_and_file_errors_map_to_status_codes(client, session):
    paper = await make_paper(session, "/missing.pdf", page_count=1)
    anchor = {"paper_id": str(paper.id), "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "q"}

    bad_rect = await client.post("/api/notes", json={"anchor": {**anchor, "bbox": [[1, 2, 3]]}})
    page_out_of_range = await client.post("/api/notes", json={"anchor": {**anchor, "page": 5}})
    unknown_paper = await client.post("/api/notes", json={"anchor": {**anchor, "paper_id": str(uuid.uuid4())}})
    missing_file = await client.get(f"/api/papers/{paper.id}/file")

    assert bad_rect.status_code == 422
    assert page_out_of_range.status_code == 422
    assert unknown_paper.status_code == 404
    assert missing_file.status_code == 404


async def test_a_papers_notes_include_one_on_the_whole_paper_with_its_papers(client, session):
    paper = await make_paper(session, "/nonexistent.pdf")
    note = await paper_only_note(session, paper)

    listed = (await client.get(f"/api/papers/{paper.id}/notes")).json()

    assert [(n["id"], n["paper_ids"], n["anchors"]) for n in listed] == [(str(note.id), [str(paper.id)], [])]


async def test_the_notes_list_gives_every_note_a_papers_notes_or_those_on_no_paper(client, session):
    paper = await make_paper(session, "/nonexistent.pdf")
    on_paper, loose = await paper_only_note(session, paper), await paper_only_note(session)

    every = {n["id"] for n in (await client.get("/api/notes")).json()}
    by_paper = (await client.get(f"/api/notes?paper={paper.id}")).json()
    unlinked = {n["id"] for n in (await client.get("/api/notes?paper=none")).json()}
    unknown = await client.get(f"/api/notes?paper={uuid.uuid4()}")
    bogus = await client.get("/api/notes?paper=bogus")

    assert {str(on_paper.id), str(loose.id)} <= every
    assert [(n["id"], n["paper_ids"]) for n in by_paper] == [(str(on_paper.id), [str(paper.id)])]
    assert str(loose.id) in unlinked and str(on_paper.id) not in unlinked
    assert (unknown.status_code, bogus.status_code) == (404, 422)


async def test_putting_a_notes_papers_replaces_them(client, session):
    first, second = await make_paper(session, "/a.pdf"), await make_paper(session, "/b.pdf")
    note = await paper_only_note(session, first)
    url = f"/api/notes/{note.id}/papers"

    moved = await client.put(url, json={"paper_ids": [str(second.id)]})
    unknown_note = await client.put(f"/api/notes/{uuid.uuid4()}/papers", json={"paper_ids": []})
    unknown_paper = await client.put(url, json={"paper_ids": [str(uuid.uuid4())]})
    too_many = await client.put(url, json={"paper_ids": [str(uuid.uuid4()) for _ in range(101)]})

    assert (moved.status_code, moved.json()["paper_ids"]) == (200, [str(second.id)])
    assert unknown_note.status_code == 404
    assert (unknown_paper.status_code, unknown_paper.json()) == (404, {"detail": "unknown_paper"})
    assert too_many.status_code == 422


ANCHOR = {"page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "a passage"}


async def test_a_kind_is_stored_on_an_anchored_note_and_on_a_whole_paper_note(client, session, tmp_path):
    paper = await make_paper(session, str(tmp_path / "p.pdf"))
    anchored = await client.post(
        "/api/notes", json={"body": "b", "kind": "summary", "anchor": {**ANCHOR, "paper_id": str(paper.id)}}
    )
    whole = await client.post("/api/notes", json={"body": "w", "kind": "five_cs", "paper_id": str(paper.id)})
    assert (anchored.status_code, anchored.json()["kind"]) == (201, "summary")
    assert (whole.status_code, whole.json()["kind"], whole.json()["anchors"]) == (201, "five_cs", [])
    assert (await client.get(f"/api/papers/{paper.id}/notes")).json()[0]["id"] == whole.json()["id"]


async def test_create_refusals(client, session, tmp_path):
    paper = await make_paper(session, str(tmp_path / "p.pdf"))
    anchor = {**ANCHOR, "paper_id": str(paper.id)}
    both = await client.post("/api/notes", json={"body": "b", "anchor": anchor, "paper_id": str(paper.id)})
    neither = await client.post("/api/notes", json={"body": "b"})
    bogus = await client.post("/api/notes", json={"body": "b", "kind": "bogus", "paper_id": str(paper.id)})
    missing = await client.post("/api/notes", json={"body": "b", "paper_id": str(uuid.uuid4())})
    empty = await client.post("/api/notes", json={"body": " ", "paper_id": str(paper.id)})
    assert [r.status_code for r in (both, neither, bogus, missing, empty)] == [422, 422, 422, 404, 422]
    assert empty.json()["detail"] == "empty_body"


async def test_patching_a_kind_sets_it_and_null_clears_it(client, session, tmp_path):
    paper = await make_paper(session, str(tmp_path / "p.pdf"))
    note = (await client.post("/api/notes", json={"body": "b", "paper_id": str(paper.id)})).json()
    url = f"/api/notes/{note['id']}"
    set_ = await client.patch(url, json={"kind": "assumption"})
    cleared = await client.patch(url, json={"kind": None})
    assert (set_.status_code, set_.json()["kind"], cleared.status_code, cleared.json()["kind"]) == (
        200, "assumption", 200, None
    )
    assert (await client.patch(url, json={"kind": "bogus"})).status_code == 422
    assert (await client.patch(url, json={})).status_code == 422
