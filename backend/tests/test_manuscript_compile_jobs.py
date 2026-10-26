from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import manuscript_history, manuscripts, queue
from app.core.latex_compile import CompileResult
from app.models import ManuscriptCiteKey
from app.workers import manuscripts as worker

pytestmark = pytest.mark.anyio

OK = CompileResult(ok=True, pdf=b"%PDF-new", log="fine", errors=[], friendly=None)
BAD = CompileResult(ok=False, pdf=None, log="boom", errors=[{"file": "main.tex", "line": 3, "message": "x",
                                                            "kind": "error"}], friendly=None)


@pytest.fixture(autouse=True)
def wiring(session, arq, pdf_dir, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)


def fake_compile(monkeypatch, *results, seen=None):
    queue_ = list(results)

    async def compile_dir(workdir, main_file, **kw):
        if seen is not None:
            seen.append({p.relative_to(workdir).as_posix(): p.read_bytes() for p in workdir.rglob("*") if p.is_file()})
        return queue_.pop(0) if len(queue_) > 1 else queue_[0]

    monkeypatch.setattr(worker, "compile_dir", compile_dir)


async def new(session, **kw):
    return await manuscripts.create(session, title="M", template="article", workspace_id=None)


async def test_request_queues_once_then_asks_again(session, arq):
    m = await new(session)
    now = datetime.now(UTC)
    assert await manuscripts.request_compile(session, m.id, now=now) == "queued"
    assert await manuscripts.request_compile(session, m.id, now=now) == "again"
    assert [j[0] for j in arq.jobs] == ["compile_manuscript"]
    assert (await manuscripts.get(session, m.id)).compile_requested is True


@pytest.mark.parametrize(("age", "outcome"), [(119, "again"), (121, "queued")])
async def test_the_stale_window_boundary(session, arq, age, outcome):
    m = await new(session)
    now = datetime.now(UTC)
    await manuscripts.request_compile(session, m.id, now=now - timedelta(seconds=age))
    assert await manuscripts.request_compile(session, m.id, now=now) == outcome


async def test_a_request_after_the_pass_stored_its_result_queues_a_new_job(session, arq, monkeypatch):
    m = await new(session)
    mid = m.id
    await manuscripts.request_compile(session, mid, now=datetime.now(UTC))
    fake_compile(monkeypatch, OK)
    await worker.compile_manuscript({}, str(mid))  # the pass is over: status ok
    assert await manuscripts.request_compile(session, mid, now=datetime.now(UTC)) == "queued"
    assert [j[0] for j in arq.jobs] == ["compile_manuscript", "compile_manuscript"]


async def test_deleting_a_manuscript_removes_its_pdf(session):
    m = await new(session)
    path = manuscripts.pdf_path(m.id)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF")
    await manuscripts.delete(session, m.id)
    assert not path.exists()
    m2 = await new(session)
    await manuscripts.delete(session, m2.id)  # no PDF: nothing to remove, no error


async def test_enqueue_failure_marks_failed(session, monkeypatch):
    m = await new(session)

    async def boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(queue, "enqueue", boom)
    with pytest.raises(RuntimeError):
        await manuscripts.request_compile(session, m.id, now=datetime.now(UTC))
    assert (await manuscripts.get(session, m.id)).compile_status == "failed"


async def test_success_writes_pdf_snapshot_and_status(session, monkeypatch):
    m = await new(session)
    await manuscripts.put_binary(session, m.id, "figs/a.png", b"\x89PNG")
    seen = []
    fake_compile(monkeypatch, OK, seen=seen)
    await worker.compile_manuscript({}, str(m.id))
    m = await manuscripts.get(session, m.id)
    assert (m.compile_status, m.compile_log, m.compiled_at is not None) == ("ok", "fine", True)
    assert manuscripts.pdf_path(m.id).read_bytes() == b"%PDF-new"
    assert "compile" in [s.reason for s in await manuscript_history.list_(session, m.id)]
    assert seen[0]["figs/a.png"] == b"\x89PNG" and "main.tex" in seen[0] and "paperlab.bib" in seen[0]


async def test_failure_keeps_the_previous_pdf_and_stores_errors(session, monkeypatch):
    m = await new(session)
    fake_compile(monkeypatch, OK, BAD)
    await worker.compile_manuscript({}, str(m.id))
    await worker.compile_manuscript({}, str(m.id))
    m = await manuscripts.get(session, m.id)
    assert (m.compile_status, m.compile_log, m.compile_errors[0]["line"]) == ("failed", "boom", 3)
    assert manuscripts.pdf_path(m.id).read_bytes() == b"%PDF-new"


async def test_compile_again_runs_a_second_pass_in_the_same_job(session, monkeypatch):
    m = await new(session)
    calls = []

    async def compile_dir(workdir, main_file, **kw):
        calls.append(1)
        if len(calls) == 1:  # a request arrives during the first pass
            await manuscripts.request_compile(session, m.id, now=datetime.now(UTC))
        return OK

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    await manuscripts.request_compile(session, m.id, now=datetime.now(UTC))
    await worker.compile_manuscript({}, str(m.id))
    m = await manuscripts.get(session, m.id)
    assert len(calls) == 2 and m.compile_requested is False and m.compile_status == "ok"


async def test_bib_written_beside_the_sources_pins_cited_keys(session, monkeypatch):
    from app.core import workspaces
    from app.models import Paper, Workspace

    ws = Workspace(name="W")
    session.add(ws)
    paper = Paper(title="Deep Things", file_path="/x.pdf", authors=["Jane Smith"], year=2021)
    session.add(paper)
    await session.flush()
    await workspaces.add_paper(session, ws.id, paper.id)
    m = await manuscripts.create(session, title="M", template="article", workspace_id=ws.id)
    await manuscripts.upsert_text(session, m.id, "main.tex", "\\cite{smith2021deep}")
    seen = []
    fake_compile(monkeypatch, OK, seen=seen)
    await worker.compile_manuscript({}, str(m.id))
    assert "smith2021deep" in seen[0]["paperlab.bib"].decode()
    keys = await session.scalars(select(ManuscriptCiteKey.key).where(ManuscriptCiteKey.manuscript_id == m.id))
    assert list(keys) == ["smith2021deep"]


async def test_an_unexpected_error_leaves_it_failed_not_running(session, monkeypatch):
    m = await new(session)

    async def compile_dir(*a, **k):
        raise ValueError("kaput")

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    mid = m.id  # the rollback after the failure expires `m`
    await worker.compile_manuscript({}, str(mid))
    m = await manuscripts.get(session, mid)
    assert m.compile_status == "failed" and "ValueError" in m.compile_log


async def test_a_deleted_manuscript_ends_quietly(session, monkeypatch):
    m = await new(session)
    mid = str(m.id)
    await manuscripts.delete(session, m.id)
    fake_compile(monkeypatch, OK)
    await worker.compile_manuscript({}, mid)


@pytest.mark.parametrize("result", [OK, BAD])
async def test_deleted_during_the_compile_writes_nothing(session, monkeypatch, result, caplog):
    m = await new(session)
    mid = m.id

    async def compile_dir(workdir, main_file, **kw):
        await manuscripts.delete(session, mid)
        return result

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    await worker.compile_manuscript({}, str(mid))
    assert not manuscripts.pdf_path(mid).exists()
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    assert await manuscript_history.list_(session, mid) == []


async def test_files_outside_the_workdir_are_skipped(tmp_path):
    (tmp_path / "w").mkdir()
    worker._write_files(tmp_path / "w", [("../evil.txt", "x", None), ("ok/a.tex", "hi", None)])
    assert not (tmp_path / "evil.txt").exists() and (tmp_path / "w/ok/a.tex").read_text() == "hi"


async def test_the_first_compile_makes_the_pdf_folder_private_to_root(session, pdf_dir, monkeypatch):
    pdf_dir.mkdir(exist_ok=True)
    pdf_dir.chmod(0o755)
    monkeypatch.setattr(worker, "_PDF_DIR_LOCKED", False)
    fake_compile(monkeypatch, OK)
    m = await new(session)
    await worker.compile_manuscript({}, str(m.id))
    assert pdf_dir.stat().st_mode & 0o777 == 0o700
    pdf_dir.chmod(0o755)  # once per process: a later compile leaves the mode alone
    await worker.compile_manuscript({}, str(m.id))
    assert pdf_dir.stat().st_mode & 0o777 == 0o755
