"""The MCP against the owner's editor on real, separate connections (the shared test session can't show locking)."""

import asyncio
import base64
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import manuscript_agent as agent
from app.core import manuscript_history, manuscripts
from app.core.errors import Conflict
from app.models import Manuscript, ManuscriptSnapshot
from tests.conftest import TEST_DATABASE_URL

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # commits real rows


@pytest.fixture
async def real():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = []

    async def new():
        async with maker() as s:
            made = await agent.create_manuscript(s, "Race")
            ids.append(made.id)
            return made.id

    try:
        yield new, maker
    finally:
        async with maker() as s:
            await s.execute(delete(Manuscript).where(Manuscript.id.in_(ids)))  # snapshots/files cascade
            await s.commit()
        await engine.dispose()


async def base_of(maker, mid):
    async with maker() as s:
        return (await manuscripts.read(s, mid, "main.tex")).updated_at


async def mcp_snapshots(maker, mid):
    async with maker() as s:
        return await s.scalar(
            select(func.count())
            .select_from(ManuscriptSnapshot)
            .where(ManuscriptSnapshot.manuscript_id == mid, ManuscriptSnapshot.reason == manuscript_history.MCP_REASON)
        )


async def owner_save(maker, mid, text, base):
    async with maker() as s:
        await manuscripts.save_text(s, mid, "main.tex", text, base=base)
        await s.commit()


async def mcp_write(maker, mid, text, base):
    async with maker() as s:
        return await agent.write_file(s, mid, "main.tex", text, base)


async def test_owner_saves_first_then_the_mcp_write_with_the_old_base_is_refused(real):
    new, maker = real
    mid = await new()
    base = await base_of(maker, mid)
    await owner_save(maker, mid, "owner", base)
    with pytest.raises(Conflict, match="file_changed"):
        await mcp_write(maker, mid, "claude", base)
    async with maker() as s:
        assert await manuscripts.get_text(s, mid, "main.tex") == "owner"
    assert await mcp_snapshots(maker, mid) == 0


async def test_mcp_lands_first_then_the_owners_autosave_is_the_existing_conflict(real):
    new, maker = real
    mid = await new()
    base = await base_of(maker, mid)
    await mcp_write(maker, mid, "claude", base)
    with pytest.raises(Conflict, match="file_changed"):
        await owner_save(maker, mid, "owner", base)
    async with maker() as s:
        assert await manuscripts.get_text(s, mid, "main.tex") == "claude"
    assert await mcp_snapshots(maker, mid) == 1


async def test_both_at_once_with_the_same_base_one_wins_and_one_is_file_changed(real):
    new, maker = real
    mid = await new()
    base = await base_of(maker, mid)
    results = await asyncio.gather(
        owner_save(maker, mid, "owner", base), mcp_write(maker, mid, "claude", base), return_exceptions=True
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(failures) == 1 and isinstance(failures[0], Conflict) and str(failures[0]) == "file_changed"
    async with maker() as s:
        final = await manuscripts.get_text(s, mid, "main.tex")
    mcp_won = not isinstance(results[1], BaseException)
    assert final == ("claude" if mcp_won else "owner")
    assert await mcp_snapshots(maker, mid) == (1 if mcp_won else 0)


async def test_an_edit_is_refused_when_the_owner_saves_between_its_read_and_its_save(real, monkeypatch):
    """The caller's base is newer than the row (the manuscript's own updated_at, say), so only the row's own
    updated_at can catch the owner save that lands after the unlocked read."""
    new, maker = real
    mid = await new()
    late_base = datetime.now(timezone.utc) + timedelta(
        hours=1
    )  # newer than any save: only the row's own time can catch it
    owner_base = await base_of(maker, mid)
    original_save = manuscripts.save_text

    async def owner_first(session, *args, **kwargs):
        async with maker() as other:  # the owner's autosave commits after our read, before our save
            await original_save(other, mid, "main.tex", "OWNER typed", base=owner_base)
            await other.commit()
        return await original_save(session, *args, **kwargs)

    monkeypatch.setattr(manuscripts, "save_text", owner_first)
    async with maker() as s:
        with pytest.raises(Conflict, match="file_changed"):
            await agent.edit_file(s, mid, "main.tex", "\\documentclass", "\\documentclass[x]", late_base)
    async with maker() as s:
        assert await manuscripts.get_text(s, mid, "main.tex") == "OWNER typed"
    assert await mcp_snapshots(maker, mid) == 0


async def test_two_adds_of_the_same_new_figure_one_wins_and_the_bytes_are_the_winners(real):
    new, maker = real
    mid = await new()

    async def add(data):
        async with maker() as s:
            return await agent.add_figure(s, mid, "figs/a.png", base64.b64encode(data).decode())

    results = await asyncio.gather(add(b"one"), add(b"two!"), return_exceptions=True)
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(failures) == 1 and isinstance(failures[0], Conflict) and str(failures[0]) == "file_exists"
    winner = next(d for d, r in zip((b"one", b"two!"), results) if not isinstance(r, BaseException))
    async with maker() as s:
        assert (await manuscripts.read(s, mid, "figs/a.png")).data == winner


async def test_a_racing_new_path_is_file_exists_for_create_and_rename(real, monkeypatch):
    """The other writer's row commits after our existence check: the unique index decides, and we say file_exists."""
    new, maker = real
    mid = await new()
    async with maker() as s:
        await agent.create_file(s, mid, "taken.tex", "t")
        await agent.create_file(s, mid, "other.tex", "o")
        other = (await manuscripts.read(s, mid, "other.tex")).updated_at
    real_file = manuscripts._file

    async def blind(session, manuscript_id, path, *, lock=False):
        row = await real_file(session, manuscript_id, path, lock=lock)
        return None if path == "taken.tex" else row

    monkeypatch.setattr(manuscripts, "_file", blind)
    async with maker() as s:
        with pytest.raises(Conflict, match="file_exists"):
            await agent.rename_file(s, mid, "other.tex", "taken.tex", other)
    async with maker() as s:
        with pytest.raises(Conflict, match="file_exists"):
            await agent.create_file(s, mid, "taken.tex", "c")
