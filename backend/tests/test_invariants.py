"""Architecture rules and migrations, checked on every test run instead of by memory."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND = Path(__file__).resolve().parents[1]


def test_core_never_imports_fastapi():
    # Keeps app.core reusable by the MCP server (brief: enforced invariant).
    offenders = [p.name for p in (BACKEND / "app/core").rglob("*.py") if "fastapi" in p.read_text()]
    assert offenders == []


def alembic(database_url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


@pytest.mark.anyio
async def test_migrations_upgrade_downgrade_upgrade(database_url):
    """Runs against a throwaway database, never the dev one: downgrade drops every table."""
    url = make_url(database_url)
    name = f"paperlab_migrations_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    scratch_url = url.set(database=name)
    try:
        dsn = scratch_url.render_as_string(hide_password=False)
        alembic(dsn, "upgrade", "head")
        alembic(dsn, "downgrade", "base")
        alembic(dsn, "upgrade", "head")

        scratch = create_async_engine(scratch_url)
        async with scratch.connect() as conn:
            tables = (await conn.execute(text("SELECT to_regclass('chunks'), to_regclass('edges')"))).one()
        await scratch.dispose()
        assert all(tables)
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
