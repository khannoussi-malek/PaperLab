"""Architecture rules and migrations, checked on every test run instead of by memory."""

import ast
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND = Path(__file__).resolve().parents[1]


def test_core_never_imports_fastapi():
    # Keeps app.core reusable by the MCP server (brief: enforced invariant).
    offenders = [p.name for p in (BACKEND / "app/core").rglob("*.py") if "fastapi" in p.read_text()]
    assert offenders == []


def test_mcp_server_has_no_sql_and_imports_only_core_services():
    """Tool bodies stay thin (roadmap M6): any logic, and every query, belongs in app.core."""
    source = (BACKEND / "mcp_server/server.py").read_text()
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    ours = {name for name in imported if name.split(".")[0] == "app"}
    others = {name.split(".")[0] for name in imported - ours} - set(sys.stdlib_module_names)
    assert ours and all(name == "app.db" or name.split(".")[:2] == ["app", "core"] for name in ours), ours
    assert others == {"mcp", "pydantic"}  # pydantic only for tool argument bounds (Field), never models or logic
    assert [word for word in ("sqlalchemy", "select(", "text(", "execute(") if word in source] == []


@pytest.mark.parametrize(
    "module",
    [
        "app.providers.llm",
        "app.providers.embedding",
        "app.core.retrieval",
        "app.core.embedding_sources",
        "app.core.chat",
    ],
)
def test_each_module_imports_first_without_a_cycle(module):
    """Providers never import core at module level (M25): whichever of these a process imports first, it loads."""
    result = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=BACKEND, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_lock_has_no_torch():
    """M23: the search model runs on ONNX Runtime, so torch and the libraries that ran it on torch stay out."""
    locked = set(re.findall(r'^name = "([^"]+)"$', (BACKEND / "uv.lock").read_text(), re.MULTILINE))
    assert {"onnxruntime", "tokenizers", "numpy"} <= locked
    assert {"torch", "sentence-transformers", "transformers"} & locked == set()


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
        chunks, links, edges = (
            await conn.execute(text("SELECT to_regclass('chunks'), to_regclass('paper_links'), to_regclass('edges')"))
        ).one()
    await scratch.dispose()
    assert chunks and links
    # 0011 drops the empty table 0001 created (D110).
    assert edges is None


@pytest.mark.anyio
async def test_0050_round_trip(scratch_url):
    """Upgrade, downgrade refuses while a PDF-less paper exists, then succeeds, then upgrade again."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    scratch = create_async_engine(scratch_url)
    async with scratch.begin() as conn:
        await conn.execute(text("INSERT INTO papers (title, file_path) VALUES ('No file', NULL)"))
    refused = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0049"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": dsn},
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "papers without a PDF exist; delete them first" in refused.stderr
    async with scratch.begin() as conn:
        await conn.execute(text("DELETE FROM papers WHERE file_path IS NULL"))
    await scratch.dispose()
    alembic(dsn, "downgrade", "0049")
    alembic(dsn, "upgrade", "head")


@pytest.mark.anyio
async def test_0051_round_trip(scratch_url):
    """Upgrade, downgrade refuses while a hit awaits its PDF, then succeeds, then upgrade again."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    scratch = create_async_engine(scratch_url)
    async with scratch.begin() as conn:
        await conn.execute(
            text(
                "WITH ws AS (INSERT INTO workspaces (name) VALUES ('W') RETURNING id), "
                "run AS (INSERT INTO workspace_search_runs (workspace_id, query_text, sources_json, status) "
                "SELECT id, 'q', '[]', 'exhausted' FROM ws RETURNING id, workspace_id) "
                "INSERT INTO workspace_search_hits (workspace_id, run_id, source_method, normalized_title, "
                "acquisition_status) SELECT workspace_id, id, 'database_search', 't', 'awaiting_pdf' FROM run"
            )
        )
    refused = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0050"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": dsn},
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "hits awaiting a PDF exist; set them back to failed first" in refused.stderr
    async with scratch.begin() as conn:
        await conn.execute(text("UPDATE workspace_search_hits SET acquisition_status = 'failed'"))
    await scratch.dispose()
    alembic(dsn, "downgrade", "0050")
    alembic(dsn, "upgrade", "head")


@pytest.mark.anyio
async def test_0052_round_trip(scratch_url):
    """paper_merges takes merged and reported rows only; downgrade refuses while the history has rows, then drops it."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    scratch = create_async_engine(scratch_url)
    row = "INSERT INTO paper_merges (kept_id, merged_id, status) VALUES (gen_random_uuid(), gen_random_uuid(), :s)"
    async with scratch.begin() as conn:
        await conn.execute(text(row), {"s": "merged"})
        moved = (await conn.execute(text("SELECT moved FROM paper_merges"))).scalar_one()
    assert moved == {}
    with pytest.raises(IntegrityError, match="ck_paper_merges_status"):
        async with scratch.begin() as conn:
            await conn.execute(text(row), {"s": "pending"})
    refused = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0051"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": dsn},
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "paper merges are recorded; delete them first" in refused.stderr
    async with scratch.begin() as conn:
        await conn.execute(text("DELETE FROM paper_merges"))
    alembic(dsn, "downgrade", "0051")
    async with scratch.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('paper_merges')"))).scalar_one() is None
    await scratch.dispose()
    alembic(dsn, "upgrade", "head")


@pytest.mark.anyio
async def test_0053_round_trip(scratch_url):
    """The re-check and provenance columns start empty, paper_events takes two kinds and goes with its paper, and
    downgrade refuses while a paper has history, then drops it all."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    scratch = create_async_engine(scratch_url)
    async with scratch.begin() as conn:
        paper = (await conn.execute(text("INSERT INTO papers (title) VALUES ('P') RETURNING id"))).scalar_one()
        columns = "SELECT field_sources, pdf_checked_at, pdf_check_result FROM papers"
        assert tuple((await conn.execute(text(columns))).one()) == ({}, None, None)
        await conn.execute(text("INSERT INTO paper_sources (id) VALUES (true) ON CONFLICT DO NOTHING"))
        assert (await conn.execute(text("SELECT pdf_recheck_enabled FROM paper_sources"))).scalar_one() is True
        await conn.execute(text("UPDATE papers SET pdf_check_result = 'none', pdf_checked_at = now()"))
        event = "INSERT INTO paper_events (paper_id, kind) VALUES (:p, :k)"
        await conn.execute(text(event), {"p": paper, "k": "pdf_found"})
        detail = (await conn.execute(text("SELECT detail FROM paper_events"))).scalar_one()
    assert detail == {}
    with pytest.raises(IntegrityError, match="ck_papers_pdf_check_result"):
        async with scratch.begin() as conn:
            await conn.execute(text("UPDATE papers SET pdf_check_result = 'maybe'"))
    with pytest.raises(IntegrityError, match="ck_paper_events_kind"):
        async with scratch.begin() as conn:
            await conn.execute(text(event), {"p": paper, "k": "pdf_lost"})
    refused = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0052"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": dsn},
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "paper events are recorded; delete them first" in refused.stderr
    async with scratch.begin() as conn:
        await conn.execute(text("DELETE FROM papers"))  # its events go with it
        assert (await conn.execute(text("SELECT count(*) FROM paper_events"))).scalar_one() == 0
    alembic(dsn, "downgrade", "0052")
    async with scratch.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('paper_events')"))).scalar_one() is None
        left = "SELECT column_name FROM information_schema.columns WHERE column_name = ANY(:names)"
        names = ["pdf_checked_at", "pdf_check_result", "field_sources", "pdf_recheck_enabled"]
        assert (await conn.execute(text(left), {"names": names})).all() == []
    await scratch.dispose()
    alembic(dsn, "upgrade", "head")


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


@pytest.mark.anyio
async def test_the_setup_flag_starts_done_only_for_a_library_that_has_papers(scratch_url):
    """R9: an existing library (papers before this migration) never sees the first-run setup; an empty one does. If the
    migration is renumbered (K21), its PREV revision below moves with it."""
    dsn = scratch_url.render_as_string(hide_password=False)
    scratch = create_async_engine(scratch_url)
    alembic(dsn, "upgrade", "head")
    async with scratch.connect() as conn:
        empty = await conn.scalar(text("SELECT done FROM setup"))

    alembic(dsn, "downgrade", "0011")
    async with scratch.begin() as conn:
        await conn.execute(
            text("INSERT INTO papers (id, title, file_path) VALUES (:p, 'P', '/p.pdf')"), {"p": uuid.uuid4()}
        )
    alembic(dsn, "upgrade", "head")
    async with scratch.connect() as conn:
        with_papers = await conn.scalar(text("SELECT done FROM setup"))
        rows = await conn.scalar(text("SELECT count(*) FROM setup"))
    await scratch.dispose()

    assert (empty, with_papers, rows) == (False, True, 1)


@pytest.mark.anyio
async def test_the_search_source_is_one_row_that_keeps_its_connection(scratch_url):
    """D151 on a throwaway database: every test's session shadows the dev database's table (conftest), so the table's
    own rules are checked here. One row; Built-in has neither connection nor model; a connection search uses can't be
    deleted even by a caller that forgets to ask."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    scratch = create_async_engine(scratch_url)
    ids = {"id": uuid.uuid4()}
    try:
        async with scratch.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO llm_connections (id, kind, label, base_url) "
                    "VALUES (:id, 'ollama', 'Ollama', 'http://localhost:11434')"
                ),
                ids,
            )
            await conn.execute(
                text(
                    "INSERT INTO embedding_source (kind, connection_id, model) "
                    "VALUES ('ollama', :id, 'nomic-embed-text')"
                ),
                ids,
            )
        for refused in (
            "INSERT INTO embedding_source (kind) VALUES ('builtin')",  # a second row
            "INSERT INTO embedding_source (id, kind) VALUES (false, 'builtin')",  # the key can only be true
            "UPDATE embedding_source SET kind = 'voyage'",  # 768 dimensions only (D131)
            "UPDATE embedding_source SET kind = 'builtin'",  # Built-in with a connection
            "UPDATE embedding_source SET model = NULL",  # a connection's source without a model
            "DELETE FROM llm_connections",  # NO ACTION: search uses it
        ):
            with pytest.raises(IntegrityError):
                async with scratch.begin() as conn:
                    await conn.execute(text(refused))
        async with scratch.begin() as conn:
            await conn.execute(text("UPDATE embedding_source SET kind = 'builtin', connection_id = NULL, model = NULL"))
            await conn.execute(text("DELETE FROM llm_connections"))  # free once search no longer uses it
    finally:
        await scratch.dispose()


@pytest.mark.anyio
async def test_note_papers_migration_links_every_anchored_pair_and_cascades(scratch_url):
    """Notes written at 0017, the head when M20's branch was cut, gain one link per note and paper they have a passage
    on. If the migration is renumbered (K21), this upgrade target moves with it. The cascade is checked here, on a
    throwaway database, so a broken cascade can be planted without touching the owner's."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "0017")
    first, second, note = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ids = {"a": first, "b": second, "n": note}
    scratch = create_async_engine(scratch_url)
    async with scratch.begin() as conn:
        await conn.execute(
            text("INSERT INTO papers (id, title, file_path) VALUES (:a, 'A', '/a.pdf'), (:b, 'B', '/b.pdf')"), ids
        )
        await conn.execute(text("INSERT INTO notes (id, body, provenance) VALUES (:n, 'n', 'human')"), ids)
        # Two passages on the first paper and one on the second: two links, not three.
        await conn.execute(
            text(
                "INSERT INTO note_anchors (note_id, paper_id, page, bbox, quoted_text) VALUES "
                "(:n, :a, 1, '[[1, 2, 3, 4]]', 'q'), (:n, :a, 2, '[[1, 2, 3, 4]]', 'q'), "
                "(:n, :b, 1, '[[1, 2, 3, 4]]', 'q')"
            ),
            ids,
        )

    alembic(dsn, "upgrade", "head")

    async with scratch.begin() as conn:
        links = sorted((await conn.execute(text("SELECT note_id, paper_id FROM note_papers"))).all())
        await conn.execute(text("DELETE FROM note_papers WHERE note_id = :n AND paper_id = :a"), ids)
        left = (await conn.execute(text("SELECT paper_id FROM note_anchors"))).scalars().all()
    with pytest.raises(IntegrityError, match="note_anchors_note_paper_fkey"):
        async with scratch.begin() as conn:
            await conn.execute(
                text("INSERT INTO note_anchors (note_id, paper_id, page, bbox) VALUES (:n, :a, 3, '[[1, 2, 3, 4]]')"),
                ids,
            )
    async with scratch.begin() as conn:
        await conn.execute(text("DELETE FROM papers WHERE id = :b"), ids)
        kept = (await conn.execute(text("SELECT count(*) FROM notes WHERE id = :n"), ids)).scalar_one()
        links_after = (await conn.execute(text("SELECT count(*) FROM note_papers"))).scalar_one()
    await scratch.dispose()
    assert links == sorted([(note, first), (note, second)])
    assert left == [second]
    assert (kept, links_after) == (1, 0)


@pytest.mark.anyio
async def test_0058_round_trip(scratch_url):
    """M16: section_role_overrides and llm_outputs.lens exist at head, and go on a downgrade to the revision before
    (PREV, `0057`). If the migration is renumbered (K21), PREV here moves with it."""
    dsn = scratch_url.render_as_string(hide_password=False)
    alembic(dsn, "upgrade", "head")
    scratch = create_async_engine(scratch_url)
    lens_default = (
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'llm_outputs' AND column_name = 'lens'"
    )
    async with scratch.connect() as conn:
        table = (await conn.execute(text("SELECT to_regclass('section_role_overrides')"))).scalar()
        default = (await conn.execute(text(lens_default))).scalar()
    alembic(dsn, "downgrade", "0057")
    async with scratch.connect() as conn:
        gone = (await conn.execute(text("SELECT to_regclass('section_role_overrides')"))).scalar()
        no_lens = (await conn.execute(text(lens_default))).scalar()
    await scratch.dispose()
    assert table is not None and default == "'full'::text"
    assert gone is None and no_lens is None
