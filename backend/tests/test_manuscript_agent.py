import base64
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core import manuscript_agent as agent
from app.core import manuscript_history, manuscript_templates, manuscripts
from app.core import manuscript_paths as paths
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Manuscript, ManuscriptSnapshot, Workspace

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # list_all reads every manuscript
PNG = base64.b64encode(b"\x89PNG fake").decode()


async def new(session, template="article", workspace=None):
    return (await agent.create_manuscript(session, "Draft", template, workspace)).id


async def snaps(session, mid, reason=manuscript_history.MCP_REASON):
    return list(
        await session.scalars(
            select(ManuscriptSnapshot).where(
                ManuscriptSnapshot.manuscript_id == mid, ManuscriptSnapshot.reason == reason
            )
        )
    )


async def updated(session, mid, path):
    return (await manuscripts.read(session, mid, path)).updated_at


async def text(session, mid, path):
    return await manuscripts.get_text(session, mid, path)


async def code(coro, kind):
    with pytest.raises(kind) as info:
        await coro
    return str(info.value), info.value.details


# --- create / list ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("template", list(manuscript_templates.TEMPLATES))
async def test_create_each_template_with_and_without_a_workspace(session, template):
    session.add(Workspace(name="Review X"))
    await session.flush()
    for ws in (None, " Review X "):
        made = await agent.create_manuscript(session, "  T  ", template, ws)
        assert made.title == "T" and made.main_file == "main.tex"
        assert made.workspace == (None if ws is None else "Review X")
        assert "main.tex" in {f.path for f in made.files} and all(f.kind == "text" for f in made.files)
    listed = await agent.list_manuscripts(session, "Review X")
    assert [m.workspace for m in listed] == ["Review X"]


async def test_create_refusals(session):
    session.add(Workspace(name="Only"))
    await session.flush()
    msg, details = await code(agent.create_manuscript(session, "T", "article", "Nope"), NotFound)
    assert msg == "unknown_workspace" and details["available"] == ["Only"]
    msg, details = await code(agent.create_manuscript(session, "T", "nope"), InvalidInput)
    assert msg == "unknown_template" and details["available"] == list(manuscript_templates.TEMPLATES)
    for title in ("   ", "x" * 201):
        assert (await code(agent.create_manuscript(session, title), InvalidInput))[0] == "bad_title"
    assert len((await agent.create_manuscript(session, "x" * 200, "article")).title) == 200


async def test_list_manuscripts_newest_first_and_stale_running_reads_failed(session):
    a, b = await new(session), await new(session)
    await manuscripts.update(session, a, title="A")  # touches it: now the newest
    old = await agent.list_manuscripts(session, None)
    assert [m.id for m in old][:2] == [a, b]
    await session.execute(
        Manuscript.__table__.update()
        .where(Manuscript.id == b)
        .values(compile_status="running", compile_started_at=datetime.now(timezone.utc) - timedelta(days=1))
    )
    listed = {m.id: m for m in await agent.list_manuscripts(session, None)}
    assert listed[b].compile_status == "failed" and listed[a].compile_status == "never"
    assert set(vars(listed[a])) == {"id", "title", "workspace", "main_file", "compile_status", "updated_at"}
    assert (await code(agent.list_manuscripts(session, "zzz"), NotFound))[0] == "unknown_workspace"


# --- list / read -----------------------------------------------------------------------------------------------


async def test_list_files_has_no_text_and_shows_binaries(session):
    mid = await new(session)
    await agent.add_figure(session, mid, "figs/a.png", PNG)
    listing = await agent.list_files(session, mid)
    assert listing.main_file == "main.tex" and listing.title == "Draft" and listing.manuscript_id == mid
    kinds = {f.path: f.kind for f in listing.files}
    assert kinds["figs/a.png"] == "binary" and kinds["main.tex"] == "text"
    assert not any(hasattr(f, "text") for f in listing.files) and "paperlab.bib" not in kinds


async def test_read_file_whole_range_and_refusals(session):
    mid = await new(session)
    await agent.write_file(session, mid, "main.tex", "a\nb\nc\n", await updated(session, mid, "main.tex"))
    whole = await agent.read_file(session, mid, "main.tex")
    assert (whole.text, whole.total_lines, whole.start_line, whole.end_line, whole.size) == ("a\nb\nc\n", 3, 1, 3, 6)
    assert whole.updated_at == await updated(session, mid, "main.tex")
    part = await agent.read_file(session, mid, "main.tex", 2, 99)
    assert (part.text, part.start_line, part.end_line, part.total_lines) == ("b\nc\n", 2, 3, 3)
    assert part.updated_at == whole.updated_at and part.size == 6
    assert (await agent.read_file(session, mid, "main.tex", 1, 1)).text == "a\n"
    assert (await code(agent.read_file(session, mid, "main.tex", 3, 2), InvalidInput))[0] == "bad_line_range"
    assert (await code(agent.read_file(session, mid, "main.tex", 0, 2), InvalidInput))[0] == "bad_line_range"
    await agent.add_figure(session, mid, "a.png", PNG)
    assert (await code(agent.read_file(session, mid, "a.png"), InvalidInput))[0] == "binary_file"
    for missing in ("nope.tex", "paperlab.bib"):
        assert (await code(agent.read_file(session, mid, missing), NotFound))[0] == "unknown_file"


# --- create / write / edit -------------------------------------------------------------------------------------


async def test_create_file_and_file_exists_takes_no_snapshot(session):
    mid = await new(session)
    out = await agent.create_file(session, mid, "notes.md", "hi")
    assert (out.path, out.size) == ("notes.md", 2) and out.snapshot_id is not None
    assert out.updated_at == await updated(session, mid, "notes.md")
    before = len(await snaps(session, mid))
    assert (await code(agent.create_file(session, mid, "notes.md", "x"), Conflict))[0] == "file_exists"
    assert len(await snaps(session, mid)) == before and await text(session, mid, "notes.md") == "hi"


async def test_write_file_snapshots_the_old_text_and_restore_brings_it_back(session):
    mid = await new(session)
    old = await text(session, mid, "main.tex")
    out = await agent.write_file(session, mid, "main.tex", "NEW", await updated(session, mid, "main.tex"))
    assert out.size == 3 and out.snapshot_id and await text(session, mid, "main.tex") == "NEW"
    (snap,) = await snaps(session, mid)
    assert snap.id == out.snapshot_id and snap.files["main.tex"] == old
    await manuscript_history.restore(session, mid, snap.id)
    assert await text(session, mid, "main.tex") == old


async def test_write_file_refusals_leave_no_snapshot(session, monkeypatch):
    mid = await new(session)
    base = await updated(session, mid, "main.tex")
    await agent.write_file(session, mid, "main.tex", "mine", base)  # `base` is now stale
    count = len(await snaps(session, mid))
    msg, details = await code(agent.write_file(session, mid, "main.tex", "theirs", base), Conflict)
    assert msg == "file_changed" and details["updated_at"] == await updated(session, mid, "main.tex")
    assert await text(session, mid, "main.tex") == "mine"
    now = datetime.now(timezone.utc)
    assert (await code(agent.write_file(session, mid, "ghost.tex", "x", now), NotFound))[0] == "unknown_file"
    cur = await updated(session, mid, "main.tex")
    msg, details = await code(agent.write_file(session, mid, "main.tex", "x" * (paths.MAX_TEXT + 1), cur), Conflict)
    assert msg == "file_too_large" and details["limit"] == paths.MAX_TEXT
    monkeypatch.setattr(paths, "MAX_TOTAL", 100)
    assert (await code(agent.write_file(session, mid, "main.tex", "x" * 200, cur), Conflict))[
        0
    ] == "manuscript_too_large"
    assert len(await snaps(session, mid)) == count and await text(session, mid, "main.tex") == "mine"


async def test_too_many_files_is_its_own_code(session, monkeypatch):
    mid = await new(session)
    monkeypatch.setattr(paths, "MAX_FILES", len((await agent.list_files(session, mid)).files))
    assert (await code(agent.create_file(session, mid, "more.tex", "x"), Conflict))[0] == "too_many_files"
    assert not await snaps(session, mid)


async def test_edit_file_cases(session):
    mid = await new(session)
    await agent.write_file(session, mid, "main.tex", "one\ntwo\nthree two\n", await updated(session, mid, "main.tex"))
    cur = lambda: updated(session, mid, "main.tex")  # noqa: E731
    out = await agent.edit_file(session, mid, "main.tex", "one\ntwo", "1\n2 \\x 100%", await cur())
    assert await text(session, mid, "main.tex") == "1\n2 \\x 100%\nthree two\n" and out.snapshot_id
    count = len(await snaps(session, mid))
    assert (await code(agent.edit_file(session, mid, "main.tex", "zzz", "y", await cur()), Conflict))[0] == "no_match"
    msg, details = await code(agent.edit_file(session, mid, "main.tex", "t", "y", await cur()), Conflict)
    assert msg == "ambiguous_match" and details["count"] == 2
    assert (await code(agent.edit_file(session, mid, "main.tex", "", "y", await cur()), InvalidInput))[
        0
    ] == "empty_old_text"
    stale = (await cur()) - timedelta(seconds=1)
    msg, details = await code(agent.edit_file(session, mid, "main.tex", "three", "y", stale), Conflict)
    assert msg == "file_changed" and details["updated_at"] == await cur()
    assert len(await snaps(session, mid)) == count


def test_apply_edit_pure():
    assert agent.apply_edit("a b a", "b", "\\1 %s") == "a \\1 %s a"
    with pytest.raises(Conflict) as info:
        agent.apply_edit("aa", "a", "b")
    assert info.value.details == {"count": 2}


# --- rename / delete / figure ----------------------------------------------------------------------------------


async def test_rename_file_does_not_rewrite_references(session):
    mid = await new(session)
    await agent.create_file(session, mid, "a.tex", "A")
    main = await text(session, mid, "main.tex")
    await manuscripts.save_text(
        session, mid, "main.tex", main + "\\input{a}", base=await updated(session, mid, "main.tex")
    )
    out = await agent.rename_file(session, mid, "a.tex", "b.tex", await updated(session, mid, "a.tex"))
    assert (out.path, out.new_path) == ("a.tex", "b.tex") and out.snapshot_id
    assert out.updated_at == await updated(session, mid, "b.tex") and await text(session, mid, "b.tex") == "A"
    assert (await text(session, mid, "main.tex")).endswith("\\input{a}")  # pinned: references are the caller's


async def test_rename_and_delete_refusals(session):
    mid = await new(session)
    await agent.add_figure(session, mid, "a.png", PNG)
    await agent.create_file(session, mid, "a.tex", "A")
    await agent.create_file(session, mid, "b.tex", "B")
    count = len(await snaps(session, mid))
    base = await updated(session, mid, "a.tex")
    main_base = await updated(session, mid, "main.tex")
    fig_base = await updated(session, mid, "a.png")
    assert (await code(agent.rename_file(session, mid, "main.tex", "z.tex", main_base), Conflict))[0] == "main_file"
    assert (await code(agent.rename_file(session, mid, "a.png", "b.png", fig_base), InvalidInput))[0] == "binary_file"
    assert (await code(agent.rename_file(session, mid, "a.tex", "b.tex", base), Conflict))[0] == "file_exists"
    assert (await code(agent.rename_file(session, mid, "a.tex", "paperlab.bib", base), InvalidInput))[
        0
    ] == "reserved_path"
    assert (await code(agent.rename_file(session, mid, "a.tex", "a.png", base), InvalidInput))[
        0
    ] == "unsupported_file_type"
    assert (await code(agent.delete_file(session, mid, "main.tex", main_base), Conflict))[0] == "main_file"
    assert (await code(agent.delete_file(session, mid, "a.png", fig_base), InvalidInput))[0] == "binary_file"
    stale = base - timedelta(seconds=1)
    assert (await code(agent.delete_file(session, mid, "a.tex", stale), Conflict))[0] == "file_changed"
    assert (await code(agent.rename_file(session, mid, "a.tex", "c.tex", stale), Conflict))[0] == "file_changed"
    assert len(await snaps(session, mid)) == count


async def test_delete_file_snapshots_and_restore_brings_it_back(session):
    mid = await new(session)
    await agent.create_file(session, mid, "a.tex", "A")
    out = await agent.delete_file(session, mid, "a.tex", await updated(session, mid, "a.tex"))
    assert out.path == "a.tex" and out.snapshot_id and await text(session, mid, "a.tex") is None
    await manuscript_history.restore(session, mid, out.snapshot_id)
    assert await text(session, mid, "a.tex") == "A"


async def test_add_figure(session, monkeypatch):
    mid = await new(session)
    out = await agent.add_figure(session, mid, "figs/a.png", PNG)
    assert (out.path, out.size) == ("figs/a.png", len(b"\x89PNG fake"))
    assert out.updated_at == await updated(session, mid, "figs/a.png") and not await snaps(session, mid)
    assert (await code(agent.add_figure(session, mid, "x.tex", PNG), InvalidInput))[0] == "unsupported_file_type"
    assert (await code(agent.add_figure(session, mid, "figs/a.png", PNG), Conflict))[0] == "file_exists"
    assert (await code(agent.add_figure(session, mid, "b.png", "!!!notbase64"), InvalidInput))[0] == "bad_base64"
    big = base64.b64encode(bytes(paths.MAX_BINARY + 1)).decode()
    msg, details = await code(agent.add_figure(session, mid, "c.png", big), Conflict)
    assert msg == "file_too_large" and details["limit"] == paths.MAX_BINARY


async def test_paperlab_bib_is_never_listed(session):
    mid = await new(session)
    assert "paperlab.bib" not in {f.path for f in (await agent.list_files(session, mid)).files}


HOSTILE = {
    "paperlab.bib": "reserved_path",
    "a/b/PaperLab.BIB": "reserved_path",
    "../x.tex": "bad_path",
    "/etc/x.tex": "bad_path",
    "a//b.tex": "bad_path",
    "a/b/c/d/e.tex": "bad_path",
    "main.tex\0": "bad_path",
    "x.exe": "unsupported_file_type",
    "é.tex": "bad_path",
}


@pytest.mark.parametrize("path", HOSTILE)
async def test_hostile_paths_are_refused_everywhere_with_no_row_and_no_snapshot(session, path):
    mid = await new(session)
    want, now = HOSTILE[path], datetime.now(timezone.utc)
    rows = (await agent.list_files(session, mid)).files
    calls = [
        agent.create_file(session, mid, path, "x"),
        agent.write_file(session, mid, path, "x", now),
        agent.edit_file(session, mid, path, "a", "b", now),
        agent.add_figure(session, mid, path, PNG),
        agent.rename_file(session, mid, "main.tex", path, now),
    ]
    if path.endswith(".png"):
        calls.pop()
    for call in calls:
        with pytest.raises((InvalidInput, NotFound)) as info:
            await call
        assert str(info.value) == want, call
    assert (await agent.list_files(session, mid)).files == rows and not await snaps(session, mid)


async def test_a_store_failure_leaves_no_snapshot_and_the_text_unchanged(session, monkeypatch):
    mid = await new(session)
    old, base = await text(session, mid, "main.tex"), await updated(session, mid, "main.tex")

    async def boom(*a, **k):
        raise RuntimeError("disk")

    monkeypatch.setattr(manuscripts, "_store", boom)
    with pytest.raises(RuntimeError):
        await agent.write_file(session, mid, "main.tex", "NEW", base)
    assert not await snaps(session, mid) and await text(session, mid, "main.tex") == old
    assert await session.scalar(select(func.count()).select_from(Manuscript)) >= 1  # the session is usable


# --- the base must be exactly the file's updated_at ------------------------------------------------------------


async def _two_saves(session):
    mid = await new(session)
    first = await updated(session, mid, "main.tex")
    await agent.write_file(session, mid, "main.tex", "one", first)
    return mid, first, await updated(session, mid, "main.tex")


@pytest.mark.parametrize("which", ["future", "between"])
async def test_a_guessed_base_is_file_changed_for_write_rename_and_delete(session, which):
    mid, first, second = await _two_saves(session)
    await agent.create_file(session, mid, "a.tex", "a")
    row_time = await updated(session, mid, "a.tex")
    guess = (
        datetime.now(timezone.utc) + timedelta(hours=1) if which == "future" else row_time + timedelta(microseconds=1)
    )
    calls = [
        agent.write_file(session, mid, "a.tex", "x", guess),
        agent.rename_file(session, mid, "a.tex", "b.tex", guess),
        agent.delete_file(session, mid, "a.tex", guess),
    ]
    for call in calls:
        msg, details = await code(call, Conflict)
        assert msg == "file_changed" and details["updated_at"] == row_time
    assert await text(session, mid, "a.tex") == "a"
    cur = await updated(session, mid, "main.tex")
    await agent.write_file(session, mid, "main.tex", "ok", cur)  # the exact base works
    await agent.rename_file(session, mid, "a.tex", "b.tex", row_time)
    await agent.delete_file(session, mid, "b.tex", await updated(session, mid, "b.tex"))
