"""The first-run setup's one flag (spec §5): while it isn't done, the app opens #/setup on start. One row, `setup`,
which the migration presets to done for a library that already has papers."""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setup


async def is_done(session: AsyncSession) -> bool:
    # populate_existing: after an upsert the identity map may still hold the row as it was loaded.
    row = await session.get(Setup, True, populate_existing=True)
    return row is not None and row.done


async def set_done(session: AsyncSession, done: bool) -> bool:
    await session.execute(
        insert(Setup)
        .values(id=True, done=done)
        .on_conflict_do_update(index_elements=[Setup.id], set_={"done": done, "updated_at": func.now()})
    )
    await session.commit()
    return done
