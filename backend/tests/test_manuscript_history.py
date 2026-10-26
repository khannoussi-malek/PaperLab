from datetime import datetime, timedelta, timezone

import pytest

from app.core import manuscript_history as history
from app.core import manuscripts
from app.core.errors import Conflict
from app.models import ManuscriptSnapshot

pytestmark = pytest.mark.anyio


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
    assert len(before) == 1 and set(before[0].files) == {"main.tex", "extra.tex"}


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
