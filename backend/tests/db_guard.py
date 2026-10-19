"""M77: refuse to run the tests on the live database while this branch carries a migration it hasn't had.

Tests run on the live database inside rolled-back transactions by design, but a branch whose models know a column
the live schema lacks fails there (or worse), and that is how a run without TEST_DATABASE_URL once reached it.
"""

import asyncio
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

LIVE_DATABASE = "paperlab"
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def refusal(db_name: str | None, db_version: str | None, lineage: list[str]) -> str | None:
    """Why the run must stop, or None. `lineage` is the code's head first, then its ancestors."""
    head = lineage[0]
    if db_name != LIVE_DATABASE or db_version == head:
        return None
    if db_version is not None and db_version not in lineage:
        return None  # the database is ahead of this code (another branch migrated it): not this guard's case
    return (
        f"This branch has migration {head}, which the live database '{LIVE_DATABASE}' doesn't have"
        f" (it is at {db_version or 'no version'}). Set TEST_DATABASE_URL to a throwaway database"
        " (paperlab_mNN, migrated with alembic) and run again."
    )


def code_lineage() -> list[str]:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    return [rev.revision for rev in script.iterate_revisions(script.get_current_head(), "base")]


async def _db_version(url: str) -> str | None:
    engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            if not await connection.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL")):
                return None
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


def check(url: str) -> str | None:
    """The refusal for this test database URL, or None. Only the live database is ever asked."""
    if make_url(url).database != LIVE_DATABASE:
        return None
    return refusal(LIVE_DATABASE, asyncio.run(_db_version(url)), code_lineage())
