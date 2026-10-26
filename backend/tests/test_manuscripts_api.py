import io
import uuid
import zipfile

import pytest

from app.core import manuscripts, queue
from app.core.errors import Conflict
from app.models import Workspace

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # lists orphans, which are global
TEX = "\\documentclass{article}\\begin{document}Hi\\end{document}"


@pytest.fixture(autouse=True)
def wiring(arq, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)


async def make(client, **body):
    response = await client.post("/api/manuscripts", json={"title": "Draft", "template": "article", **body})
    assert response.status_code == 201, response.text
    return response.json()


async def test_templates_listed(client):
    body = (await client.get("/api/templates/manuscripts")).json()
    assert {"name": "article", "label": "Plain article"} in body


async def test_create_get_patch_delete(client, session):
    ws = Workspace(name=f"W {uuid.uuid4().hex[:6]}")
    session.add(ws)
    await session.flush()
    m = await make(client, workspace_id=str(ws.id))
    assert m["workspace_id"] == str(ws.id)
    got = (await client.get(f"/api/manuscripts/{m['id']}")).json()
    assert [f["path"] for f in got["files"]] == ["main.tex"] and got["compile_status"] == "never"
    patched = await client.patch(f"/api/manuscripts/{m['id']}", json={"title": "New", "workspace_id": None})
    assert patched.json()["title"] == "New" and patched.json()["workspace_id"] is None
    assert (await client.patch(f"/api/manuscripts/{m['id']}", json={"main_file": "x.md"})).status_code == 422
    assert (await client.patch(f"/api/manuscripts/{m['id']}", json={"main_file": "nope.tex"})).status_code == 404
    patch = await client.patch(f"/api/manuscripts/{m['id']}", json={"checklist": {"a": True}})
    assert patch.json()["checklist"] == {"a": True}
    assert (await client.patch(f"/api/manuscripts/{m['id']}", json={"title": None})).status_code == 422
    assert (await client.delete(f"/api/manuscripts/{m['id']}")).status_code == 204
    assert (await client.get(f"/api/manuscripts/{m['id']}")).status_code == 404
    assert (await client.post("/api/manuscripts", json={"title": "x", "template": "nope"})).status_code == 422
    assert (await client.post("/api/manuscripts", json={"title": "x", "template": "article",
                                                        "workspace_id": str(uuid.uuid4())})).status_code == 404


async def test_list_by_workspace_and_orphans_after_workspace_delete(client, session):
    ws = Workspace(name=f"W {uuid.uuid4().hex[:6]}")
    session.add(ws)
    await session.flush()
    m = await make(client, workspace_id=str(ws.id))
    listed = (await client.get(f"/api/workspaces/{ws.id}/manuscripts")).json()
    assert [x["id"] for x in listed] == [m["id"]]
    assert m["id"] not in [x["id"] for x in (await client.get("/api/manuscripts?orphans=true")).json()]
    assert (await client.delete(f"/api/workspaces/{ws.id}")).status_code == 204
    assert m["id"] in [x["id"] for x in (await client.get("/api/manuscripts?orphans=true")).json()]
    assert (await client.get("/api/manuscripts")).status_code == 422  # only the orphan listing exists


async def test_file_get_put_and_stale_put_is_409_with_updated_at(client):
    m = await make(client)
    url = f"/api/manuscripts/{m['id']}/files/main.tex"
    first = (await client.get(url)).json()
    assert first["path"] == "main.tex" and "documentclass" in first["text"]
    saved = await client.put(url, json={"text": "v2", "base_updated_at": first["updated_at"]})
    assert saved.status_code == 200 and saved.json()["updated_at"] > first["updated_at"]
    stale = await client.put(url, json={"text": "v3", "base_updated_at": first["updated_at"]})
    assert stale.status_code == 409 and stale.json()["detail"] == "file_changed"
    assert stale.json()["updated_at"] == saved.json()["updated_at"]
    assert (await client.get(url)).json()["text"] == "v2"
    assert (await client.put(url, json={"text": "x", "base_updated_at": "2026-01-01T00:00:00"})).status_code == 422
    assert (await client.put(url, json={"text": "x"})).status_code == 409  # exists, no base
    new = await client.put(f"/api/manuscripts/{m['id']}/files/ch/one.tex", json={"text": "c"})
    assert new.status_code == 200
    assert (await client.get(f"/api/manuscripts/{m['id']}/files/none.tex")).status_code == 404
    assert (await client.put(f"/api/manuscripts/{m['id']}/files/a.exe", json={"text": "c"})).status_code == 422


async def test_uploads_binary_text_rename_delete(client):
    m = await make(client)
    base = f"/api/manuscripts/{m['id']}"
    up = await client.post(f"{base}/uploads", data={"path": "fig/a.png"}, files={"file": ("a.png", b"\x89PNG")})
    assert up.status_code == 201
    raw = await client.get(f"{base}/files/fig/a.png")
    assert raw.content == b"\x89PNG" and raw.headers["content-type"] == "image/png"
    txt = await client.post(f"{base}/uploads", data={"path": "refs.bib"}, files={"file": ("r.bib", b"@a{b}")})
    assert txt.status_code == 201
    again = await client.post(f"{base}/uploads", data={"path": "refs.bib"}, files={"file": ("r.bib", b"@a{b}")})
    assert again.status_code == 409 and again.json()["detail"] == "file_exists"
    bad = await client.post(f"{base}/uploads", data={"path": "x.bib"}, files={"file": ("r.bib", b"\xff\xfe")})
    assert bad.status_code == 422 and bad.json()["detail"] == "not_text"
    escape = await client.post(f"{base}/uploads", data={"path": "../x.png"}, files={"file": ("x", b"1")})
    assert escape.status_code == 422
    moved = await client.post(f"{base}/files/refs.bib/rename", json={"new_path": "lit.bib"})
    assert moved.status_code == 200 and moved.json()["path"] == "lit.bib"
    assert (await client.post(f"{base}/files/nope.bib/rename", json={"new_path": "z.bib"})).status_code == 404
    assert (await client.delete(f"{base}/files/lit.bib")).status_code == 204
    assert (await client.delete(f"{base}/files/lit.bib")).status_code == 404
    assert (await client.delete(f"{base}/files/main.tex")).status_code == 409


async def test_upload_over_the_cap_is_refused_whatever_content_length_says(client, monkeypatch):
    from app.core import manuscript_paths
    monkeypatch.setattr(manuscript_paths, "MAX_BINARY", 10)
    m = await make(client)
    response = await client.post(f"/api/manuscripts/{m['id']}/uploads", data={"path": "a.png"},
                                 files={"file": ("a.png", b"x" * 50)})
    assert response.status_code == 409 and response.json()["detail"] == "file_too_large"


async def test_compile_twice_is_queued_then_again(client, arq):
    m = await make(client)
    first = await client.post(f"/api/manuscripts/{m['id']}/compile")
    second = await client.post(f"/api/manuscripts/{m['id']}/compile")
    assert (first.status_code, first.json()) == (202, {"state": "queued"})
    assert second.json() == {"state": "again"}
    assert [j[0] for j in arq.jobs] == ["compile_manuscript"]
    assert (await client.post(f"/api/manuscripts/{uuid.uuid4()}/compile")).status_code == 404


async def test_pdf_404_before_first_compile_then_served(client):
    m = await make(client)
    missing = await client.get(f"/api/manuscripts/{m['id']}/pdf")
    assert missing.status_code == 404 and missing.json()["detail"] == "no_pdf"
    target = manuscripts.pdf_path(uuid.UUID(m["id"]))
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4")
    ok = await client.get(f"/api/manuscripts/{m['id']}/pdf")
    assert ok.status_code == 200 and ok.content == b"%PDF-1.4" and ok.headers["content-type"] == "application/pdf"


async def test_snapshot_restore_round_trip(client, session):
    from app.core import manuscript_history
    m = await make(client)
    base = f"/api/manuscripts/{m['id']}"
    snap = await manuscript_history.take(session, uuid.UUID(m["id"]), "autosave")
    await client.put(f"{base}/files/main.tex", json={"text": "changed",
                     "base_updated_at": (await client.get(f"{base}/files/main.tex")).json()["updated_at"]})
    listed = (await client.get(f"{base}/snapshots")).json()
    assert listed[0]["id"] == str(snap.id) and listed[0]["reason"] == "autosave"
    assert (await client.post(f"{base}/snapshots/{snap.id}/restore")).status_code == 204
    assert (await client.post(f"{base}/snapshots/{uuid.uuid4()}/restore")).status_code == 404
    assert "documentclass" in (await client.get(f"{base}/files/main.tex")).json()["text"]


async def test_import_then_export_round_trip(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("main.tex", TEX + "\\cite{k}")
        z.writestr("fig/a.png", b"\x89PNG")
        z.writestr("paperlab.bib", "@old{x}")
    imported = await client.post("/api/manuscripts/import", files={"file": ("p.zip", buf.getvalue())})
    assert imported.status_code == 201
    m = imported.json()
    names = [f["path"] for f in m["files"]]
    assert names == ["fig/a.png", "main.tex", "paperlab-imported.bib"] and m["title"] == "p"
    out = await client.get(f"/api/manuscripts/{m['id']}/export.zip")
    assert out.status_code == 200 and out.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(out.content)) as z:
        assert {"main.tex", "fig/a.png", "paperlab.bib", "latexmkrc", "paperlab-imported.bib"} <= set(z.namelist())
        assert z.read("fig/a.png") == b"\x89PNG"
    assert (await client.get(f"/api/manuscripts/{uuid.uuid4()}/export.zip")).status_code == 404


async def test_import_errors_and_all_or_nothing(client, monkeypatch):
    assert (await client.post("/api/manuscripts/import", files={"file": ("p.zip", b"nope")})).status_code == 422
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("main.tex", TEX)
        z.writestr("a.txt", "1234567890")
    real, calls = manuscripts._check_caps, []

    async def second_file_hits_a_cap(*args):
        calls.append(1)
        if len(calls) == 2:
            raise Conflict("manuscript_too_large")
        await real(*args)

    monkeypatch.setattr(manuscripts, "_check_caps", second_file_hits_a_cap)
    before = len((await client.get("/api/manuscripts?orphans=true")).json())
    response = await client.post("/api/manuscripts/import", files={"file": ("p.zip", buf.getvalue())})
    assert response.status_code == 409 and len(calls) == 2
    assert len((await client.get("/api/manuscripts?orphans=true")).json()) == before
