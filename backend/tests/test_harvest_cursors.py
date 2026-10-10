from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.harvest import HarvestCursor

pytestmark = pytest.mark.anyio


async def test_a_fresh_source_has_no_cursor_row(session):
    result = await session.execute(select(HarvestCursor).where(HarvestCursor.source == "iacr_eprint"))
    assert result.scalar_one_or_none() is None


async def test_a_cursor_row_can_be_created_and_updated(session):
    session.add(HarvestCursor(source="iacr_eprint", last_synced_at=None))
    await session.flush()

    row = (await session.execute(select(HarvestCursor).where(HarvestCursor.source == "iacr_eprint"))).scalar_one()
    assert row.last_synced_at is None

    row.last_synced_at = datetime(2026, 10, 10, tzinfo=UTC)
    await session.flush()

    refreshed = (
        await session.execute(select(HarvestCursor).where(HarvestCursor.source == "iacr_eprint"))
    ).scalar_one()
    assert refreshed.last_synced_at is not None
