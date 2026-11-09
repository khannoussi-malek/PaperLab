import uuid
from datetime import datetime, timedelta, timezone

import pytest
from test_manuscript_papers import setup

from app.core import manuscripts
from app.core.errors import InvalidInput, NotFound
from app.core.manuscript_checks import service
from app.core.manuscript_checks.base import Check

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


async def put(session, m, path, text):
    await manuscripts.upsert_text(session, m.id, path, text)


async def test_context_has_normalised_text_files_known_keys_and_manuscript_info(session):
    _, _, m = await setup(session, "Deep learning")
    await put(session, m, "main.tex", "a\r\nb \\cite{mine}\r\n")
    await put(session, m, "own.bib", "@article{mine, title={T}}\n")
    ctx = await service.load_context(session, m.id)
    assert ctx.files["main.tex"] == "a\nb \\cite{mine}\n"
    assert "mine" in ctx.known_keys
    assert (ctx.manuscript.main_file, ctx.manuscript.compile_status, ctx.manuscript.pdf_path) == ("main.tex", "never", None)
    assert ctx.manuscript.id == str(m.id) and ctx.manuscript.updated_at is not None


async def test_a_running_compile_with_no_live_job_reads_as_failed(session):
    _, _, m = await setup(session, "Deep learning")
    m.compile_status = "running"
    m.compile_started_at = datetime.now(timezone.utc) - timedelta(days=2)
    await session.flush()
    assert (await service.load_context(session, m.id)).manuscript.compile_status == "failed"


async def test_run_checks_runs_the_real_registry_and_writes_nothing(session):
    _, _, m = await setup(session, "Deep learning")
    await put(session, m, "main.tex", "Hi.\nSee \\cite{nowhere}.\n")
    await session.flush()
    run = await service.run_checks(session, m.id)
    assert "citations.missing_keys" in run.ran
    assert [(x.file, x.line) for x in run.findings if "nowhere" in x.message] == [("main.tex", 2)]
    assert not (session.new or session.dirty or session.deleted)


async def test_cost_filter(session, monkeypatch):
    _, _, m = await setup(session, "Deep learning")
    calls = []
    monkeypatch.setattr(service, "REGISTRY", (
        Check("a.cheap", "cheap", "d", lambda c: calls.append("cheap") or []),
        Check("b.full", "full", "d", lambda c: calls.append("full") or [])))
    assert (await service.run_checks(session, m.id, cost="cheap")).ran == ["a.cheap"]
    assert calls == ["cheap"]


async def test_names_are_validated_before_anything_is_loaded(session):
    # the manuscript does not exist: loading would raise NotFound, so InvalidInput proves the order
    with pytest.raises(InvalidInput, match="unknown_check"):
        await service.run_checks(session, uuid.uuid4(), names=["nope"])


async def test_unknown_manuscript(session):
    with pytest.raises(NotFound, match="unknown_manuscript"):
        await service.run_checks(session, uuid.uuid4())
