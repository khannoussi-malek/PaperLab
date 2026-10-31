import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from test_manuscript_papers import setup

from app.config import settings
from app.core import diagram_compile, queue
from app.core import manuscript_diagrams as md
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import LLMConnection, LLMModel
from app.models import ManuscriptDiagram as Row
from app.providers.llm import FakeLLM
from app.workers import manuscript_diagrams as worker
from app.workers import manuscript_section_review as worker_section
from app.workers import manuscripts as compile_worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
needs_bin = pytest.mark.skipif(
    not os.environ.get("TECTONIC_BIN"), reason="TECTONIC_BIN unset (scripts/tectonic-dev.sh)"
)
DESC = "An encoder feeds a decoder."
PIC = "\\begin{tikzpicture}\n\\node (a) {Encoder};\n\\node[right=of a] {Decoder};\n\\end{tikzpicture}"
REPLY = f"<tikz>\n\\usetikzlibrary{{positioning}}\n{PIC}\n</tikz>"


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


class Compiler:
    """A stand-in for diagram_compile.preview that records what it was asked to compile."""

    def __init__(self, ok=True, errors=None, friendly=None):
        self.ok, self.errors, self.friendly, self.calls = ok, errors or [], friendly, []

    async def __call__(self, libraries, picture):
        self.calls.append((libraries, picture))
        pdf = b"%PDF-fake" if self.ok else None
        return diagram_compile.PreviewResult(self.ok, pdf, self.errors, None if self.ok else self.friendly)


@pytest.fixture(autouse=True)
def wiring(session, arq, monkeypatch, local_default_model, pdf_dir):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    monkeypatch.setattr(worker_section, "SessionLocal", shared_session)  # _model resolves the default there
    monkeypatch.setattr(compile_worker, "COMPILE_LOCK", asyncio.Lock())  # a lock remembers the loop it first waited in


async def manuscript(session):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    return m


async def rows(session, mid):
    found = await session.scalars(
        select(Row).where(Row.manuscript_id == mid).order_by(Row.created_at).execution_options(populate_existing=True)
    )
    return list(found)


async def drawn(session, m, reply=REPLY, compiler=None):
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    compiler = compiler or Compiler()
    await worker.generate_manuscript_diagram({"llm": Scripted(reply), "compile": compiler}, str(out["id"]))
    return await md.state(session, m.id, out["id"]), compiler


async def age(session, did, minutes):
    old = datetime.now(UTC) - timedelta(minutes=minutes)
    await session.execute(update(Row).where(Row.id == did).values(updated_at=old, created_at=old))


async def test_create_stores_a_queued_row_and_queues_the_job(session, arq):
    m = await manuscript(session)
    out = await md.create(session, m.id, description=f"  {DESC}  ", confirm_remote=False)
    (row,) = await rows(session, m.id)
    assert (out["status"], out["description"], out["code"], out["ai"]) == ("queued", DESC, None, True)
    assert row.prompt_version == 1 and arq.jobs == [("generate_manuscript_diagram", str(row.id))]


async def test_create_keeps_the_newest_five_and_drops_week_old_rows(session):
    m = await manuscript(session)
    made = []
    for i in range(6):
        out = await md.create(session, m.id, description=f"{DESC} {i}", confirm_remote=False)
        await md.cancel(session, m.id, out["id"])
        made.append(out["id"])
    assert [r.id for r in await rows(session, m.id)] == made[1:]
    await session.execute(update(Row).where(Row.id == made[5]).values(created_at=datetime.now(UTC) - timedelta(days=8)))
    await md.create(session, m.id, description=DESC, confirm_remote=False)
    assert made[5] not in [r.id for r in await rows(session, m.id)]


@pytest.mark.parametrize("description", ["", "   ", "x" * 2001])
async def test_an_empty_or_long_description_is_invalid(session, arq, description):
    m = await manuscript(session)
    with pytest.raises(InvalidInput, match="description_invalid"):
        await md.create(session, m.id, description=description, confirm_remote=False)
    assert await rows(session, m.id) == [] and arq.jobs == []


async def test_a_live_row_blocks_and_an_old_one_reads_interrupted(session):
    m = await manuscript(session)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    with pytest.raises(Conflict, match="diagram_running"):
        await md.create(session, m.id, description=DESC, confirm_remote=False)
    await age(session, out["id"], 21)
    assert (await md.state(session, m.id, out["id"]))["status"] == "interrupted"
    assert (await md.create(session, m.id, description=DESC, confirm_remote=False))["status"] == "queued"


async def test_no_model_and_a_remote_model_needs_confirming(session, arq):
    m = await manuscript(session)
    await session.execute(update(LLMModel).values(is_default=False))
    with pytest.raises(Conflict, match="no_model"):
        await md.create(session, m.id, description=DESC, confirm_remote=False)
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await md.create(session, m.id, description=DESC, confirm_remote=False)
    assert arq.jobs == []
    assert (await md.create(session, m.id, description=DESC, confirm_remote=True))["status"] == "queued"


async def test_generation_stores_code_and_a_preview(session):
    m = await manuscript(session)
    got, compiler = await drawn(session, m)
    assert (got["status"], got["code"], got["libraries"], got["compiled"]) == ("done", PIC, ["positioning"], True)
    assert got["errors"] == [] and got["labels_not_in_description"] == [] and got["model"] == "fake:scripted"
    assert compiler.calls == [(["positioning"], PIC)]
    assert await md.pdf(session, m.id, got["id"]) == b"%PDF-fake"


async def test_a_failed_compile_is_done_with_its_errors_and_no_preview(session):
    m = await manuscript(session)
    bad = Compiler(ok=False, errors=[{"line": 2, "message": "Undefined control sequence"}], friendly="compile_error")
    got, _ = await drawn(session, m, compiler=bad)
    assert (got["status"], got["compiled"], got["reason"]) == ("done", False, "compile_error")
    assert got["errors"] == [{"line": 2, "message": "Undefined control sequence"}]
    with pytest.raises(NotFound, match="no_preview"):
        await md.pdf(session, m.id, got["id"])


@pytest.mark.parametrize(
    "reply,needle",
    [
        (REPLY.replace("positioning", "external"), "external"),
        (REPLY.replace("{Decoder}", "{Decoder}\\label{fig:x}"), "\\label"),
    ],
)
async def test_code_the_guard_refuses_is_kept_listed_and_never_compiled(session, reply, needle):
    m = await manuscript(session)
    got, compiler = await drawn(session, m, reply=reply)
    assert (got["status"], got["compiled"], compiler.calls) == ("done", False, [])
    assert got["code"] and any(needle in e["message"] and e["line"] is None for e in got["errors"])


async def test_model_failures_are_plain_reasons(session):
    m = await manuscript(session)
    got, _ = await drawn(session, m, reply="no block")  # Scripted then runs dry on the retry: an unexpected error
    assert (got["status"], got["reason"]) == ("failed", "check_failed")
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    await worker.generate_manuscript_diagram({"llm": Scripted("no block", "still none")}, str(out["id"]))
    got = await md.state(session, m.id, out["id"])
    assert (got["status"], got["reason"], got["code"]) == ("failed", "model_error", None)


async def test_set_code_rechecks_requeues_and_recompiles(session, arq):
    m = await manuscript(session)
    got, _ = await drawn(session, m)
    edited = "\\usetikzlibrary{fit}\n" + PIC.replace("Decoder", "Cache")
    out = await md.set_code(session, m.id, got["id"], edited)
    assert (out["status"], out["code"], out["libraries"], out["compiled"]) == (
        "queued",
        PIC.replace("Decoder", "Cache"),
        ["fit"],
        None,
    )
    assert out["labels_not_in_description"] == ["Cache"] and arq.jobs[-1] == (
        "compile_manuscript_diagram",
        str(got["id"]),
    )
    with pytest.raises(NotFound, match="no_preview"):
        await md.pdf(session, m.id, got["id"])
    compiler = Compiler()
    await worker.compile_manuscript_diagram({"compile": compiler}, str(got["id"]))
    done = await md.state(session, m.id, got["id"])
    assert (done["status"], done["compiled"]) == ("done", True) and compiler.calls == [(["fit"], out["code"])]
    out = await md.set_code(session, m.id, got["id"], PIC.replace("{Encoder}", "{\\input{x}}"))
    assert any("\\input" in e["message"] for e in out["errors"])
    await worker.compile_manuscript_diagram({"compile": compiler}, str(got["id"]))
    assert (await md.state(session, m.id, got["id"]))["compiled"] is False and len(compiler.calls) == 1


async def test_set_code_refuses_while_generating_and_names_an_unknown_diagram(session):
    m = await manuscript(session)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    with pytest.raises(Conflict, match="diagram_running"):
        await md.set_code(session, m.id, out["id"], PIC)
    with pytest.raises(NotFound, match="unknown_diagram"):
        await md.set_code(session, m.id, uuid.uuid4(), PIC)


async def test_a_newer_edit_supersedes_a_compile_in_flight(session):
    m = await manuscript(session)
    got, _ = await drawn(session, m)
    await md.set_code(session, m.id, got["id"], PIC.replace("Decoder", "First"))
    taken = await worker._take(got["id"])  # the first compile starts
    await md.set_code(session, m.id, got["id"], PIC.replace("Decoder", "Second"))
    await worker._write(got["id"], taken[-1], status="done", compiled=True, preview_pdf=b"%PDF-old")
    now = await md.state(session, m.id, got["id"])
    assert (now["status"], now["compiled"]) == ("queued", None) and "Second" in now["code"]


async def test_cancel_then_a_late_write_is_ignored(session):
    m = await manuscript(session)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    taken = await worker._take(out["id"])
    cancelled = await md.cancel(session, m.id, out["id"])
    await worker._write(out["id"], taken[-1], status="done", code=PIC)
    now = await md.state(session, m.id, out["id"])
    assert (cancelled["status"], cancelled["reason"], now["status"], now["code"]) == (
        "failed",
        "cancelled",
        "failed",
        None,
    )


async def test_delete_removes_only_this_manuscripts_row(session):
    m, other = await manuscript(session), await manuscript(session)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    with pytest.raises(NotFound, match="unknown_diagram"):
        await md.remove(session, other.id, out["id"])
    await md.remove(session, m.id, out["id"])
    assert await rows(session, m.id) == []


async def test_the_job_timeout_is_under_the_live_window():
    assert worker.DIAGRAM_JOB_TIMEOUT < md.LIVE.total_seconds()


@needs_bin
async def test_the_fake_model_and_real_tectonic_make_a_real_pdf(session, monkeypatch):
    monkeypatch.setattr(settings, "tectonic_bin", os.environ["TECTONIC_BIN"])
    monkeypatch.setattr(settings, "tectonic_only_cached", True)
    if os.environ.get("TECTONIC_CACHE_DIR"):
        monkeypatch.setattr(settings, "tectonic_cache_dir", Path(os.environ["TECTONIC_CACHE_DIR"]))
    m = await manuscript(session)
    out = await md.create(session, m.id, description='A "sensor" feeds a "model".', confirm_remote=False)
    await worker.generate_manuscript_diagram({"llm": FakeLLM()}, str(out["id"]))
    got = await md.state(session, m.id, out["id"])
    assert (got["status"], got["compiled"]) == ("done", True), got
    assert (await md.pdf(session, m.id, out["id"])).startswith(b"%PDF")


async def test_an_older_compile_never_overwrites_the_one_that_took_the_row_after_it(session):
    m = await manuscript(session)
    got, _ = await drawn(session, m)
    await md.set_code(session, m.id, got["id"], PIC.replace("Decoder", "First"))
    first = await worker._take(got["id"])
    await md.set_code(session, m.id, got["id"], PIC.replace("Decoder", "Second"))
    second = await worker._take(got["id"])  # running again, with a newer stamp
    await worker._write(got["id"], first[-1], status="done", compiled=True, preview_pdf=b"%PDF-old")
    assert (await md.state(session, m.id, got["id"]))["status"] == "running"
    await worker._write(got["id"], second[-1], status="done", compiled=False)
    assert (await md.state(session, m.id, got["id"]))["compiled"] is False


async def test_a_queue_that_is_down_fails_the_row(session, monkeypatch):
    async def down(*args):
        raise ConnectionError("redis is down")

    m = await manuscript(session)
    monkeypatch.setattr(queue, "enqueue", down)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    assert (out["status"], out["reason"]) == ("failed", "queue_unavailable")


async def remote_default(session):
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()


async def test_a_default_that_turns_remote_after_start_is_refused_by_the_job(session, monkeypatch):  # final M2
    m = await manuscript(session)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)  # local at start
    await remote_default(session)

    def boom(*a, **k):
        raise AssertionError("a model was built")

    monkeypatch.setattr(worker_section, "build_llm", boom)
    await worker.generate_manuscript_diagram({}, str(out["id"]))
    got = await md.state(session, m.id, out["id"])
    assert (got["status"], got["reason"], got["code"]) == ("failed", "remote_model_needs_confirm", None)
    confirmed = await md.create(session, m.id, description=DESC, confirm_remote=True)
    row = await session.get(Row, confirmed["id"])
    assert row.confirm_remote is True


async def test_the_preview_locks_the_pdf_dir_first(session, monkeypatch):  # final I2
    calls = []
    monkeypatch.setattr(compile_worker, "_lock_pdf_dir", lambda: calls.append("locked"))
    m = await manuscript(session)
    await drawn(session, m)
    assert calls == ["locked"]


async def test_a_preview_that_crashes_after_generation_keeps_the_code(session):  # final M3
    async def crash(libraries, picture):
        raise OSError("tectonic would not start")

    m = await manuscript(session)
    out = await md.create(session, m.id, description=DESC, confirm_remote=False)
    await worker.generate_manuscript_diagram({"llm": Scripted(REPLY), "compile": crash}, str(out["id"]))
    got = await md.state(session, m.id, out["id"])
    assert (got["status"], got["compiled"], got["reason"], got["code"]) == ("done", False, "compile_failed", PIC)
