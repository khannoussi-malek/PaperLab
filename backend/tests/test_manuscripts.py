from datetime import timedelta
from uuid import uuid4

import pytest

from app.core import manuscript_paths as paths
from app.core import manuscripts
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Workspace

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # this file reads all manuscripts


async def new(session, **kw):
    return await manuscripts.create(session, title="Draft", template="article", workspace_id=kw.get("workspace_id"))


async def test_create_from_template_writes_its_files(session):
    m = await new(session)
    files = await manuscripts.files(session, m.id)
    assert sorted(f.path for f in files) == sorted(
        ["main.tex"]
        + [f"sections/{s}.tex" for s in ("introduction", "related-work", "method", "results", "discussion", "conclusion")]
    )
    assert "documentclass" in (await manuscripts.read(session, m.id, "main.tex")).text
    with pytest.raises(InvalidInput, match="unknown_template"):
        await manuscripts.create(session, title="x", template="nope", workspace_id=None)


async def test_stale_save_is_file_changed_and_keeps_the_newer_text(session):
    m = await new(session)
    first = (await manuscripts.read(session, m.id, "main.tex")).updated_at  # the row is one identity-mapped object
    saved = await manuscripts.save_text(session, m.id, "main.tex", "newer", base=first)
    assert saved.updated_at > first
    with pytest.raises(Conflict, match="file_changed") as exc:
        await manuscripts.save_text(session, m.id, "main.tex", "stale", base=first)
    assert exc.value.details["updated_at"] == saved.updated_at
    assert (await manuscripts.read(session, m.id, "main.tex")).text == "newer"


async def test_save_with_no_base_refuses_an_existing_file(session):
    m = await new(session)
    with pytest.raises(Conflict, match="file_exists"):
        await manuscripts.save_text(session, m.id, "main.tex", "x", base=None)
    created = await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    assert created.size == 1


async def test_caps_refuse_large_text_binary_total_and_count(session, monkeypatch):
    m = await new(session)
    monkeypatch.setattr(paths, "MAX_TEXT", 5)
    with pytest.raises(Conflict, match="file_too_large"):
        await manuscripts.save_text(session, m.id, "a.tex", "é" * 3, base=None)  # 6 bytes
    monkeypatch.setattr(paths, "MAX_BINARY", 5)
    with pytest.raises(Conflict, match="file_too_large"):
        await manuscripts.put_binary(session, m.id, "a.png", b"123456")
    monkeypatch.setattr(paths, "MAX_TEXT", 2 * 1024**2)
    monkeypatch.setattr(paths, "MAX_TOTAL", 10_000)
    used = sum(f.size for f in await manuscripts.files(session, m.id))
    monkeypatch.setattr(paths, "MAX_TOTAL", used + 3)
    with pytest.raises(Conflict, match="manuscript_too_large"):
        await manuscripts.save_text(session, m.id, "a.tex", "1234", base=None)
    await manuscripts.save_text(session, m.id, "a.tex", "123", base=None)
    monkeypatch.setattr(paths, "MAX_FILES", 2)
    with pytest.raises(Conflict, match="too_many_files"):
        await manuscripts.save_text(session, m.id, "b.tex", "", base=None)


async def test_main_file_cannot_be_removed(session):
    m = await new(session)
    with pytest.raises(Conflict, match="main_file"):
        await manuscripts.remove(session, m.id, "main.tex")
    await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    await manuscripts.remove(session, m.id, "a.tex")
    assert "a.tex" not in [f.path for f in await manuscripts.files(session, m.id)]


async def test_rename_validates_the_new_path(session):
    m = await new(session)
    await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    with pytest.raises(InvalidInput, match="bad_path"):
        await manuscripts.rename(session, m.id, "a.tex", "../b.tex")
    with pytest.raises(Conflict, match="file_exists"):
        await manuscripts.rename(session, m.id, "a.tex", "main.tex")
    assert (await manuscripts.rename(session, m.id, "a.tex", "sec/b.tex")).path == "sec/b.tex"
    renamed_main = await manuscripts.rename(session, m.id, "main.tex", "paper.tex")
    assert renamed_main.path == "paper.tex"
    assert (await manuscripts.get(session, m.id)).main_file == "paper.tex"


async def test_list_for_none_returns_orphans_only(session):
    ws = Workspace(name="W")
    session.add(ws)
    await session.flush()
    inside = await new(session, workspace_id=ws.id)
    orphan = await new(session)
    assert [m.id for m in await manuscripts.list_for(session, workspace_id=None)] == [orphan.id]
    assert [m.id for m in await manuscripts.list_for(session, workspace_id=ws.id)] == [inside.id]


async def test_move_to_workspace(session):
    ws = Workspace(name="W")
    session.add(ws)
    await session.flush()
    m = await new(session)
    moved = await manuscripts.update(session, m.id, workspace_id=ws.id, title="T")
    assert (moved.workspace_id, moved.title, moved.updated_at > m.created_at - timedelta(1)) == (ws.id, "T", True)
    assert (await manuscripts.update(session, m.id, workspace_id=None)).workspace_id is None
    with pytest.raises(NotFound, match="unknown_workspace"):
        await manuscripts.update(session, m.id, workspace_id=uuid4())
    await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    with pytest.raises(NotFound, match="unknown_file"):
        await manuscripts.update(session, m.id, main_file="zzz.tex")
    assert (await manuscripts.update(session, m.id, main_file="a.tex")).main_file == "a.tex"


async def test_main_file_must_be_an_existing_tex_file(session):
    m = await new(session)
    await manuscripts.put_binary(session, m.id, "fig.png", b"x")
    await manuscripts.save_text(session, m.id, "refs.bib", "x", base=None)
    for path in ("fig.png", "refs.bib"):
        with pytest.raises(InvalidInput, match="main_file_not_tex"):
            await manuscripts.update(session, m.id, main_file=path)
    assert (await manuscripts.get(session, m.id)).main_file == "main.tex"
    await manuscripts.delete(session, m.id)
    with pytest.raises(NotFound, match="unknown_manuscript"):
        await manuscripts.get(session, m.id)


async def test_not_found(session):
    ghost = uuid4()
    m = await new(session)
    for call in (
        manuscripts.get(session, ghost), manuscripts.delete(session, ghost), manuscripts.files(session, ghost),
        manuscripts.update(session, ghost, title="x"), manuscripts.read(session, ghost, "main.tex"),
        manuscripts.save_text(session, ghost, "a.tex", "x", base=None),
        manuscripts.put_binary(session, ghost, "a.png", b"x"),
    ):
        with pytest.raises(NotFound, match="unknown_manuscript"):
            await call
    for call in (manuscripts.read(session, m.id, "no.tex"), manuscripts.remove(session, m.id, "no.tex"),
                 manuscripts.rename(session, m.id, "no.tex", "b.tex")):
        with pytest.raises(NotFound, match="unknown_file"):
            await call
    with pytest.raises(NotFound, match="unknown_workspace"):
        await manuscripts.create(session, title="x", template="article", workspace_id=ghost)


async def snaps(session, mid):
    from app.core import manuscript_history as history
    return await history.list_(session, mid)


async def test_save_text_with_snapshot_keeps_the_old_files_and_skips_autosave(session):
    m = await new(session)
    f = await manuscripts.save_text(session, m.id, "a.tex", "old", base=None)
    from app.core import manuscript_history as history
    await history.take(session, m.id, "compile")
    before = len(await snaps(session, m.id))
    await manuscripts.save_text(session, m.id, "a.tex", "new", base=f.updated_at, snapshot="before_mcp")
    listed = await snaps(session, m.id)
    assert len(listed) == before + 1  # the one before_mcp, no autosave beside it
    mcp = next(s for s in listed if s.reason == "before_mcp")
    assert mcp.files["a.tex"] == "old"
    assert await manuscripts.get_text(session, m.id, "a.tex") == "new"


async def test_save_text_with_snapshot_but_no_prior_snapshot_takes_the_owners_autosave_then_its_own(session):
    m = await new(session)
    await manuscripts.save_text(session, m.id, "a.tex", "x", base=None, snapshot="before_mcp")
    assert sorted(s.reason for s in await snaps(session, m.id)) == ["autosave", "before_mcp"]


async def test_a_refused_save_with_snapshot_leaves_none(session):
    m = await new(session)
    f = await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    stale = f.updated_at - timedelta(seconds=1)
    for kw in ({"base": stale}, {"base": None}):
        with pytest.raises(Conflict):
            await manuscripts.save_text(session, m.id, "a.tex", "y", snapshot="before_mcp", **kw)
    with pytest.raises(Conflict, match="file_too_large"):
        await manuscripts.save_text(session, m.id, "a.tex", "y" * (paths.MAX_TEXT + 1), base=f.updated_at,
                                    snapshot="before_mcp")
    assert all(s.reason != "before_mcp" for s in await snaps(session, m.id))


async def test_rename_and_remove_check_base_and_snapshot_once(session):
    m = await new(session)
    f = await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    stale = f.updated_at - timedelta(seconds=1)
    with pytest.raises(Conflict, match="file_changed"):
        await manuscripts.rename(session, m.id, "a.tex", "b.tex", base=stale, snapshot="before_mcp")
    with pytest.raises(Conflict, match="file_changed"):
        await manuscripts.remove(session, m.id, "a.tex", base=stale, snapshot="before_mcp")
    assert all(s.reason != "before_mcp" for s in await snaps(session, m.id))
    await manuscripts.rename(session, m.id, "a.tex", "b.tex", base=f.updated_at, snapshot="before_mcp")
    assert [s.reason for s in await snaps(session, m.id)].count("before_mcp") == 1
    g = await manuscripts.read(session, m.id, "b.tex")
    await manuscripts.remove(session, m.id, "b.tex", base=g.updated_at, snapshot="before_mcp")
    mcp = [s for s in await snaps(session, m.id) if s.reason == "before_mcp"]
    assert len(mcp) == 2 and any("b.tex" in s.files for s in mcp)


async def test_a_refused_rename_or_remove_leaves_no_snapshot(session):
    m = await new(session)
    await manuscripts.save_text(session, m.id, "a.tex", "x", base=None)
    with pytest.raises(Conflict):
        await manuscripts.remove(session, m.id, m.main_file, snapshot="before_mcp")
    with pytest.raises(NotFound):
        await manuscripts.rename(session, m.id, "nope.tex", "c.tex", snapshot="before_mcp")
    assert all(s.reason != "before_mcp" for s in await snaps(session, m.id))
