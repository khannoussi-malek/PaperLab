"""The MCP against the owner's editor on real, separate connections (the shared test session can't show locking)."""

import asyncio
from datetime import datetime, timezone

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
    assert datetime.now(timezone.utc) > (await base_of(maker, mid))
