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


@pytest.fixture
async def scratch_url(database_url):
    """A throwaway database, never the dev one: downgrade drops every table."""
    url = make_url(database_url)
    name = f"paperlab_migrations_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield url.set(database=name)
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


@pytest.mark.anyio
async def test_migrations_upgrade_downgrade_upgrade(scratch_url):
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    alembic(dsn, "downgrade", "base")
    alembic(dsn, "upgrade", "head")

    scratch = create_async_engine(scratch_url)
    async with scratch.connect() as conn:
        tables = (await conn.execute(text("SELECT to_regclass('chunks'), to_regclass('edges')"))).one()
    await scratch.dispose()
    assert all(tables)


@pytest.mark.anyio
async def test_workspaces_migration_keeps_categories_memberships_and_answers(scratch_url):
    """Data written at 0004, the revision just before the workspaces migration, survives it. If the migration is
    ever renumbered, this upgrade target moves with it."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "0004")
    paper, root, child, output = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scratch = create_async_engine(scratch_url)
    async with scratch.begin() as conn:
        await conn.execute(text("INSERT INTO papers (id, title, file_path) VALUES (:p, 'P', '/p.pdf')"), {"p": paper})
        # Legal before this migration: category names were unique per parent, not globally.
        await conn.execute(
            text("INSERT INTO categories (id, parent_id, name) VALUES (:r, NULL, 'Thesis'), (:c, :r, 'Thesis')"),
            {"r": root, "c": child},
        )
        await conn.execute(
            text("INSERT INTO paper_categories (paper_id, category_id) VALUES (:p, :c)"), {"p": paper, "c": child}
        )
        await conn.execute(
            text(
                "INSERT INTO llm_outputs (id, paper_id, kind, content, cited_chunks, model, prompt_version) "
                "VALUES (:o, :p, 'chat', 'an answer', NULL, 'm', 1)"
            ),
            {"o": output, "p": paper},
        )

    alembic(dsn, "upgrade", "head")

    async with scratch.connect() as conn:
        names = dict((await conn.execute(text("SELECT id, name FROM workspaces"))).all())
        members = (
            await conn.execute(text("SELECT workspace_id, paper_id, added_at IS NOT NULL FROM workspace_papers"))
        ).all()
        answer = (await conn.execute(text("SELECT cited_chunks, source_notes, workspace_id FROM llm_outputs"))).one()
        old = (await conn.execute(text("SELECT to_regclass('categories'), to_regclass('note_categories')"))).one()
    await scratch.dispose()
    assert names == {root: "Thesis", child: "Thesis (2)"}
    assert members == [(child, paper, True)]
    assert tuple(answer) == ([], [], None)
    assert tuple(old) == (None, None)
