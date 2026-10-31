from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core import manuscript_history as history
from app.core import manuscripts
from app.core.errors import Conflict, NotFound
from app.models import ManuscriptSnapshot

pytestmark = pytest.mark.anyio
SECTION_FILES = [
    f"sections/{s}.tex" for s in ("introduction", "related-work", "method", "results", "discussion", "conclusion")
]


async def new(session):
    return await manuscripts.create(session, title="D", template="article", workspace_id=None)


async def test_autosave_snapshots_only_after_ten_minutes(session):
    m = await new(session)
    t0 = datetime.now(timezone.utc)
    assert await history.maybe_autosave(session, m.id, now=t0) is True  # none yet
    assert await history.maybe_autosave(session, m.id, now=t0 + timedelta(minutes=9)) is False
    assert await history.maybe_autosave(session, m.id, now=t0 + timedelta(minutes=11)) is True
    snaps = await history.list_(session, m.id)
    assert [s.reason for s in snaps] == ["autosave", "autosave"]


async def test_keeps_the_newest_fifty(session):
    m = await new(session)
    for _ in range(52):
        await history.take(session, m.id, "compile")
    snaps = await history.list_(session, m.id)
    assert len(snaps) == history.KEEP == 50


async def test_restore_snapshots_first_and_matches_text_files_exactly(session):
    m = await new(session)
    await manuscripts.save_text(session, m.id, "a.tex", "old a", base=None)
    snap = await history.take(session, m.id, "compile")
    a = await manuscripts.read(session, m.id, "a.tex")
    await manuscripts.save_text(session, m.id, "a.tex", "new a", base=a.updated_at)
    await manuscripts.save_text(session, m.id, "extra.tex", "x", base=None)
    await manuscripts.remove(session, m.id, "a.tex")
    await history.restore(session, m.id, snap.id)
    listed = await manuscripts.files(session, m.id)
    files = {f.path: (await manuscripts.read(session, m.id, f.path)).text for f in listed}
    assert files == dict(snap.files)
    before = [s for s in await history.list_(session, m.id) if s.reason == "before_restore"]
    assert len(before) == 1 and set(before[0].files) == {"main.tex", "extra.tex", *SECTION_FILES}


async def test_restore_leaves_binaries(session):
    m = await new(session)
    snap = await history.take(session, m.id, "compile")
    await manuscripts.put_binary(session, m.id, "fig.png", b"png")
    await history.restore(session, m.id, snap.id)
    assert (await manuscripts.read(session, m.id, "fig.png")).data == b"png"


async def test_restore_refuses_when_the_snapshot_lacks_the_main_file(session):
    m = await new(session)
    snap = ManuscriptSnapshot(manuscript_id=m.id, reason="compile", files={"a.tex": "x"})
    session.add(snap)
    await session.flush()
    with pytest.raises(Conflict, match="main_file"):
        await history.restore(session, m.id, snap.id)


async def test_unknown_snapshot_and_another_manuscripts_snapshot(session):
    with pytest.raises(NotFound, match="unknown_snapshot"):
        await history.get(session, uuid4())
    mine, other = await new(session), await new(session)
    await manuscripts.save_text(session, other.id, "o.tex", "other", base=None)
    foreign = await history.take(session, other.id, "compile")
    await manuscripts.save_text(session, mine.id, "m.tex", "mine", base=None)
    before = len(await history.list_(session, mine.id))
    with pytest.raises(NotFound, match="unknown_snapshot"):
        await history.restore(session, mine.id, foreign.id)
    assert len(await history.list_(session, mine.id)) == before
    assert {f.path for f in await manuscripts.files(session, mine.id)} == {"m.tex", "main.tex", *SECTION_FILES}


async def test_restore_skips_files_whose_text_is_unchanged(session):
    m = await new(session)
    await manuscripts.save_text(session, m.id, "a.tex", "same", base=None)
    await manuscripts.save_text(session, m.id, "b.tex", "old", base=None)
    snap = await history.take(session, m.id, "compile")
    b = await manuscripts.read(session, m.id, "b.tex")
    await manuscripts.save_text(session, m.id, "b.tex", "new", base=b.updated_at)
    stamp = (await manuscripts.read(session, m.id, "a.tex")).updated_at
    await history.restore(session, m.id, snap.id)
    assert (await manuscripts.read(session, m.id, "a.tex")).updated_at == stamp
    assert (await manuscripts.read(session, m.id, "b.tex")).text == "old"


async def test_pruning_keeps_owner_snapshots_apart_from_mcp_ones(session):
    m = await new(session)
    for _ in range(3):
        await history.take(session, m.id, "autosave")
    for _ in range(60):
        await history.take(session, m.id, history.MCP_REASON)
    reasons = [s.reason for s in await history.list_(session, m.id)]
    assert reasons.count("autosave") == 3 and reasons.count("before_mcp") == history.MCP_KEEP == 20


async def test_mcp_snapshots_do_not_crowd_out_the_owners_fifty(session):
    m = await new(session)
    for _ in range(55):
        await history.take(session, m.id, "autosave")
    for _ in range(5):
        await history.take(session, m.id, "before_mcp")
    reasons = [s.reason for s in await history.list_(session, m.id)]
    assert reasons.count("autosave") == 50 and reasons.count("before_mcp") == 5


async def claude_write(session, mid, text):
    """What the MCP does: base is the file's updated_at, snapshot is before_mcp."""
    row = await manuscripts.read(session, mid, "main.tex")
    await manuscripts.save_text(session, mid, "main.tex", text, base=row.updated_at, snapshot=history.MCP_REASON)


async def owner_pool(session, mid):
    return [s for s in await history.list_(session, mid) if s.reason != history.MCP_REASON]


async def test_the_owners_latest_text_survives_a_long_claude_session(session):
    """The owner snapshotted at t0, typed Y two minutes later (no autosave is due), then Claude took over."""
    m = await new(session)
    await history.take(session, m.id, "autosave")  # t0
    await manuscripts.upsert_text(session, m.id, "main.tex", "OWNER Y")  # typed after t0, no snapshot of it yet
    await claude_write(session, m.id, "claude 0")
    for i in range(1, 26):
        await claude_write(session, m.id, f"claude {i}")
    assert any(s.files.get("main.tex") == "OWNER Y" for s in await owner_pool(session, m.id))


async def test_a_pure_claude_loop_adds_at_most_one_owner_snapshot(session):
    m = await new(session)
    await history.take(session, m.id, "autosave")
    before = len(await owner_pool(session, m.id))
    for i in range(30):
        await claude_write(session, m.id, f"claude {i}")
    assert len(await owner_pool(session, m.id)) <= before + 1


async def test_maybe_autosave_ignores_before_mcp_snapshots(session):
    m = await new(session)
    session.add(ManuscriptSnapshot(manuscript_id=m.id, reason=history.MCP_REASON, files={}))
    await session.flush()
    assert await history.maybe_autosave(session, m.id, now=datetime.now(timezone.utc)) is True
