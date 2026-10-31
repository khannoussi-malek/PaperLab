"""The 13 manuscript tools through an in-process client, on the test's rolled-back session."""

import base64
import uuid
from datetime import datetime, timezone

import pymupdf
import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result

from app.core import manuscript_history, manuscripts
from app.models import ManuscriptSnapshot

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
OLD = "2000-01-01T00:00:00Z"
PNG = base64.b64encode(b"\x89PNG fake").decode()


async def created(**kw):
    return result(await call("create_manuscript", title="Draft", **kw))


async def section(mid):
    files = result(await call("list_manuscript_files", manuscript_id=mid))["files"]
    return next(f for f in files if f["path"].startswith("sections/"))


def failed(response, code):
    assert response.is_error
    assert response.structured_content["error"] == code, response.structured_content
    return response.structured_content


async def test_create_list_read_edit_and_the_snapshot(session):
    made = await created()
    mid = made["id"]
    paths = [f["path"] for f in result(await call("list_manuscript_files", manuscript_id=mid))["files"]]
    assert "main.tex" in paths and any(p.startswith("sections/") for p in paths)
    info = await section(mid)
    read = result(await call("read_manuscript_file", manuscript_id=mid, path=info["path"]))
    old = read["text"]
    word = old.split()[0]

    edited = result(
        await call(
            "edit_manuscript_file",
            manuscript_id=mid,
            path=info["path"],
            old_text=word,
            new_text="CHANGED",
            base=read["updated_at"],
        )
    )
    back = result(await call("read_manuscript_file", manuscript_id=mid, path=info["path"]))
    assert back["text"] == old.replace(word, "CHANGED", 1)
    snap = await session.get(ManuscriptSnapshot, edited["snapshot_id"])
    assert snap.reason == "before_mcp" and snap.files[info["path"]] == old


async def test_a_stale_base_is_refused_and_the_text_unchanged():
    mid = (await created())["id"]
    info = await section(mid)
    before = result(await call("read_manuscript_file", manuscript_id=mid, path=info["path"]))["text"]
    body = failed(
        await call("write_manuscript_file", manuscript_id=mid, path=info["path"], text="x", base=OLD), "file_changed"
    )
    assert "updated_at" in body
    assert result(await call("read_manuscript_file", manuscript_id=mid, path=info["path"]))["text"] == before


async def test_create_twice_is_file_exists():
    mid = (await created())["id"]
    result(await call("create_manuscript_file", manuscript_id=mid, path="sections/new.tex", text="a"))
    failed(await call("create_manuscript_file", manuscript_id=mid, path="sections/new.tex", text="b"), "file_exists")


async def test_paperlab_bib_is_reserved_through_every_tool():
    mid = (await created())["id"]
    now = datetime.now(timezone.utc).isoformat()
    calls = [
        ("create_manuscript_file", {"path": "paperlab.bib", "text": "x"}),
        ("write_manuscript_file", {"path": "paperlab.bib", "text": "x", "base": now}),
        ("edit_manuscript_file", {"path": "paperlab.bib", "old_text": "a", "new_text": "b", "base": now}),
        ("rename_manuscript_file", {"path": "main.tex", "new_path": "paperlab.bib", "base": now}),
        ("delete_manuscript_file", {"path": "paperlab.bib", "base": now}),
        ("add_manuscript_figure", {"path": "paperlab.bib", "data_base64": PNG}),
    ]
    for tool, args in calls:
        failed(await call(tool, manuscript_id=mid, **args), "reserved_path")


async def test_three_mebibytes_is_too_large():
    mid = (await created())["id"]
    failed(
        await call("create_manuscript_file", manuscript_id=mid, path="sections/big.tex", text="a" * 3 * 1024**2),
        "file_too_large",
    )


async def test_figure_rename_and_delete():
    mid = (await created())["id"]
    result(await call("add_manuscript_figure", manuscript_id=mid, path="figures/a.png", data_base64=PNG))
    listed = result(await call("list_manuscript_files", manuscript_id=mid))["files"]
    assert any(f["path"] == "figures/a.png" and f["kind"] == "binary" for f in listed)

    info = await section(mid)
    renamed = result(
        await call(
            "rename_manuscript_file",
            manuscript_id=mid,
            path=info["path"],
            new_path="sections/moved.tex",
            base=info["updated_at"],
        )
    )
    deleted = result(
        await call("delete_manuscript_file", manuscript_id=mid, path="sections/moved.tex", base=renamed["updated_at"])
    )
    assert deleted["path"] == "sections/moved.tex"
    assert "sections/moved.tex" not in [
        f["path"] for f in result(await call("list_manuscript_files", manuscript_id=mid))["files"]
    ]


async def test_compile_queues_once_and_reads_back(session, jobs):
    mid = (await created())["id"]
    assert result(await call("get_compile_result", manuscript_id=mid))["status"] == "never"
    assert result(await call("compile_manuscript", manuscript_id=mid))["state"] == "queued"
    assert result(await call("compile_manuscript", manuscript_id=mid))["state"] == "again"
    assert len(jobs.jobs) == 1

    manuscript = await manuscripts.get(session, mid)
    manuscript.compile_status, manuscript.compiled_at = "ok", datetime.now(timezone.utc)
    await session.flush()
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello pdf")
    path = manuscripts.pdf_path(manuscript.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(doc.tobytes())

    view = result(await call("get_compile_result", manuscript_id=mid))
    assert (view["status"], view["finished"], view["pdf"]["available"]) == ("ok", True, True)
    pdf = result(await call("read_manuscript_pdf_text", manuscript_id=mid))
    assert "hello pdf" in pdf["pages"][0]["text"]


async def test_an_unknown_manuscript_is_refused_by_every_tool():
    ghost = "00000000-0000-4000-8000-000000000000"
    now = datetime.now(timezone.utc).isoformat()
    for tool, args in [
        ("list_manuscript_files", {}),
        ("read_manuscript_file", {"path": "main.tex"}),
        ("compile_manuscript", {}),
        ("get_compile_result", {}),
        ("read_manuscript_pdf_text", {}),
        ("delete_manuscript_file", {"path": "main.tex", "base": now}),
    ]:
        failed(await call(tool, manuscript_id=ghost, **args), "unknown_manuscript")


async def test_listing_twenty_files_carries_no_text():
    mid = (await created())["id"]
    for i in range(20):
        result(await call("create_manuscript_file", manuscript_id=mid, path=f"sections/s{i}.tex", text="body"))
    listing = result(await call("list_manuscript_files", manuscript_id=mid))
    assert len(listing["files"]) >= 20 and "text" not in str(listing.keys()) + "".join(
        str(sorted(f)) for f in listing["files"]
    )


async def test_list_manuscripts_sees_the_new_one():
    made = await created()
    assert made["id"] in [m["id"] for m in result(await call("list_manuscripts"))]


async def test_reserved_source_and_missing_source_paths():
    mid = (await created())["id"]
    now = datetime.now(timezone.utc).isoformat()
    failed(await call("delete_manuscript_file", manuscript_id=mid, path="paperlab.bib", base=now), "reserved_path")
    failed(
        await call(
            "rename_manuscript_file", manuscript_id=mid, path="paperlab.bib", new_path="sections/x.tex", base=now
        ),
        "reserved_path",
    )
    failed(await call("delete_manuscript_file", manuscript_id=mid, path="sections/ghost.tex", base=now), "unknown_file")
    failed(
        await call(
            "rename_manuscript_file", manuscript_id=mid, path="sections/ghost.tex", new_path="sections/x.tex", base=now
        ),
        "unknown_file",
    )


async def text_files(mid):
    files = result(await call("list_manuscript_files", manuscript_id=mid))["files"]
    return {
        f["path"]: result(await call("read_manuscript_file", manuscript_id=mid, path=f["path"]))["text"]
        for f in files
        if f["kind"] == "text"
    }


async def test_an_agent_writes_compiles_reads_and_the_owner_restores(session, client, jobs):
    mid = (await created())["id"]
    template = await text_files(mid)

    main = result(await call("read_manuscript_file", manuscript_id=mid, path="main.tex"))
    # a stale base fails with an updated_at that is itself a valid base on the retry
    result(await call("create_manuscript_file", manuscript_id=mid, path="sections/extra.tex", text="Extra."))
    extra = result(await call("read_manuscript_file", manuscript_id=mid, path="sections/extra.tex"))
    body = failed(
        await call("write_manuscript_file", manuscript_id=mid, path="sections/extra.tex", text="Extra 2.", base=OLD),
        "file_changed",
    )
    retried = result(
        await call(
            "write_manuscript_file",
            manuscript_id=mid,
            path="sections/extra.tex",
            text="Extra 2.",
            base=body["updated_at"],
        )
    )
    assert retried["path"] == "sections/extra.tex" and extra["updated_at"] <= body["updated_at"]

    result(
        await call(
            "edit_manuscript_file",
            manuscript_id=mid,
            path="main.tex",
            old_text="\\end{document}",
            new_text="\\input{sections/extra}\n\\end{document}",
            base=main["updated_at"],
        )
    )
    result(await call("create_manuscript_file", manuscript_id=mid, path="refs.bib", text="@book{k, title={T}}"))

    assert result(await call("compile_manuscript", manuscript_id=mid))["state"] == "queued"
    assert len(jobs.jobs) == 1
    manuscript = await manuscripts.get(session, mid)  # the worker, stubbed to succeed
    manuscript.compile_status, manuscript.compiled_at = "ok", datetime.now(timezone.utc)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "journey page")
    path = manuscripts.pdf_path(manuscript.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(doc.tobytes())
    await session.flush()
    assert result(await call("get_compile_result", manuscript_id=mid))["status"] == "ok"
    pages = result(await call("read_manuscript_pdf_text", manuscript_id=mid))["pages"]
    assert "journey page" in pages[0]["text"]

    rows = await client.get(f"/api/manuscripts/{mid}/snapshots")
    mcp = [s for s in rows.json() if s["reason"] == "before_mcp"]
    assert len(mcp) == 4
    await manuscript_history.restore(
        session, uuid.UUID(mid), uuid.UUID(mcp[-1]["id"])
    )  # the oldest: the template's files
    assert await text_files(mid) == template
