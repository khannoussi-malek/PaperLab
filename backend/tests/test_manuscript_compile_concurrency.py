"""Compile jobs on real, separate connections: the shared rolled-back test session can't show locking."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import manuscripts, queue
from app.core.latex_compile import CompileResult
from app.models import Manuscript
from app.workers import manuscripts as worker
from tests.conftest import TEST_DATABASE_URL

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # commits real rows
OK = CompileResult(ok=True, pdf=b"%PDF", log="fine", errors=[], friendly=None)


@pytest.fixture
async def real(arq, pdf_dir, monkeypatch):
    """Real, committed rows on separate connections. Yields (new, maker, made); every row `new` made is deleted after
    the test, whatever happened in it."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    made: list[AsyncSession] = []
    maker = async_sessionmaker(engine, expire_on_commit=False)

    def factory():
        made.append(maker())
        return made[-1]

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "COMPILE_LOCK", asyncio.Lock())  # a lock remembers the loop it first waited in
    ids = []

    async def new():
        async with maker() as s:
            m = await manuscripts.create(s, title="C", template="article", workspace_id=None)
            ids.append(m.id)  # before the commit: a failure there still gets cleaned
            await s.commit()
            return m.id

    try:
        yield new, maker, made
    finally:
        async with maker() as s:
            await s.execute(delete(Manuscript).where(Manuscript.id.in_(ids)))
            await s.commit()
        await engine.dispose()


async def test_no_transaction_is_open_and_a_request_is_not_blocked_while_tectonic_runs(real, monkeypatch):
    new, maker, made = real
    mid = await new()
    inside, release = asyncio.Event(), asyncio.Event()
    open_during = []

    async def compile_dir(workdir, main_file, **kw):
        open_during.extend(s.in_transaction() for s in made)
        inside.set()
        await release.wait()
        return OK

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    job = asyncio.create_task(worker.compile_manuscript({}, str(mid)))
    await asyncio.wait_for(inside.wait(), 10)
    try:
        async with maker() as other:
            answer = await asyncio.wait_for(manuscripts.request_compile(other, mid, now=datetime.now(UTC)), 2)
    finally:
        release.set()  # a failing assertion must not leave the job parked
        await asyncio.wait_for(job, 10)
    assert answer == "again" and open_during and not any(open_during)
    async with maker() as s:  # the request landed during the pass, so a second one ran and ended `ok`
        assert (await manuscripts.get(s, mid)).compile_status == "ok"


async def test_two_jobs_never_run_compile_dir_at_once(real, monkeypatch):
    new, _, _ = real
    a, b = await new(), await new()
    events = []

    async def compile_dir(workdir, main_file, **kw):
        events.append("in")
        await asyncio.sleep(0.05)
        events.append("out")
        return OK

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    await asyncio.gather(worker.compile_manuscript({}, str(a)), worker.compile_manuscript({}, str(b)))
    assert events == ["in", "out", "in", "out"]


async def test_the_stale_clock_starts_only_once_the_job_holds_the_compile_lock(real, monkeypatch):
    new, maker, _ = real
    a, b = await new(), await new()
    inside, release = asyncio.Event(), asyncio.Event()

    async def compile_dir(workdir, main_file, **kw):
        inside.set()
        await release.wait()
        return OK

    monkeypatch.setattr(worker, "compile_dir", compile_dir)
    job_a = asyncio.create_task(worker.compile_manuscript({}, str(a)))
    await asyncio.wait_for(inside.wait(), 10)
    job_b = asyncio.create_task(worker.compile_manuscript({}, str(b)))
    try:
        await asyncio.sleep(0.5)  # B is waiting for A's lock
        async with maker() as s:
            assert (await manuscripts.get(s, b)).compile_started_at is None
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(job_a, job_b), 10)
    async with maker() as s:
        assert (await manuscripts.get(s, b)).compile_started_at is not None
