"""ARQ job that pages a workspace search run to exhaustion (M30a Task 5)."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select, update

from app.core.workspace_search import PAGE_SIZE_BY_SOURCE
from app.models import PaperSources
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import discovery_fake
from app.workers import workspace_search as worker_module

pytestmark = pytest.mark.anyio


@pytest.fixture
async def worker(session, monkeypatch):
    """Same pattern as test_references_api.py's `worker` fixture: point the job's own SessionLocal at the test's
    rolled-back session, and clear any leftover paper_sources row from the shared dev DB (D15) so the defaults
    apply (arxiv on, OpenAlex off) instead of whatever a developer last configured."""
    await session.execute(delete(PaperSources))

    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker_module, "SessionLocal", shared_session)
    return {"transport": discovery_fake.transport()}


async def _new_run(session, status: str) -> WorkspaceSearchRun:
    workspace = Workspace(name=f"Worker test {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id,
        query_text="bert",
        filters_json={},
        query_overrides_json={},
        sources_json=["arxiv"],
        status=status,
        started_at=datetime.now(timezone.utc),
        stats_json={},
    )
    session.add(run)
    await session.flush()
    return run


async def test_worker_pages_until_exhausted(session, worker):
    run = await _new_run(session, "running")
    session.add(WorkspaceSearchCursor(run_id=run.id, source="arxiv", cursor_json={"value": 0}))
    await session.commit()

    await worker_module.run_workspace_search(worker, str(run.id))

    reloaded = await session.get(WorkspaceSearchRun, run.id)
    assert reloaded.status == "exhausted"
    assert reloaded.stopped_at is not None
    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(hits) >= 1  # search_batch's own merge/dedup counting is test_workspace_search_engine.py's job


async def test_worker_pages_multiple_batches_before_exhausting(session, worker, monkeypatch):
    """PAGE_SIZE_BY_SOURCE["arxiv"] (20) exceeds discovery_fake's 3-item PAGE_PAPERS list, so a real run exhausts
    after exactly one page — test_worker_pages_until_exhausted never proves the `while True` loop calls
    search_batch a second time. Shrink the page size below the fixture's item count so arXiv needs two pages,
    and count calls to prove the loop actually iterates."""
    monkeypatch.setitem(PAGE_SIZE_BY_SOURCE, "arxiv", 2)
    real_search_batch = worker_module.search_batch
    calls = 0

    async def counting_search_batch(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await real_search_batch(*args, **kwargs)

    monkeypatch.setattr(worker_module, "search_batch", counting_search_batch)

    run = await _new_run(session, "running")
    session.add(WorkspaceSearchCursor(run_id=run.id, source="arxiv", cursor_json={"value": 0}))
    await session.commit()

    await worker_module.run_workspace_search(worker, str(run.id))

    assert calls == 2  # proves the loop looped: one page (2 items) then a second (1 item) before exhausting
    reloaded = await session.get(WorkspaceSearchRun, run.id)
    assert reloaded.status == "exhausted"


async def test_worker_stops_mid_loop_on_a_concurrent_status_change(session, worker, monkeypatch):
    """Simulates the (future, Task 6) stop-run API endpoint flipping `run.status` to "stopped" via a raw UPDATE
    while a batch is in flight — the loop's session.refresh(run) + status check at the top of the next pass must
    notice and exit before the source finishes paging."""
    monkeypatch.setitem(PAGE_SIZE_BY_SOURCE, "arxiv", 2)  # needs 2 pages to exhaust — see test above
    real_search_batch = worker_module.search_batch
    calls = 0

    async def stop_after_first_batch(session_arg, providers, run_arg):
        nonlocal calls
        calls += 1
        result = await real_search_batch(session_arg, providers, run_arg)
        if calls == 1:
            await session_arg.execute(
                update(WorkspaceSearchRun).where(WorkspaceSearchRun.id == run_arg.id).values(status="stopped")
            )
        return result

    monkeypatch.setattr(worker_module, "search_batch", stop_after_first_batch)

    run = await _new_run(session, "running")
    session.add(WorkspaceSearchCursor(run_id=run.id, source="arxiv", cursor_json={"value": 0}))
    await session.commit()

    await worker_module.run_workspace_search(worker, str(run.id))

    assert calls == 1  # the loop never reached a second batch — it noticed the concurrent stop first
    reloaded = await session.get(WorkspaceSearchRun, run.id, populate_existing=True)
    assert reloaded.status == "stopped"  # not "exhausted" — set by the "concurrent" update, not the worker
    cursor = (
        await session.execute(select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id))
    ).scalar_one()
    assert cursor.exhausted is False  # exited early — the source never actually finished paging


async def test_worker_does_nothing_for_a_run_that_is_not_running(session, worker):
    run = await _new_run(session, "stopped")
    await session.commit()

    await worker_module.run_workspace_search(worker, str(run.id))

    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id)))
        .scalars()
        .all()
    )
    assert hits == []  # never even called search_batch, since it was already stopped


async def test_worker_marks_the_run_failed_on_an_unexpected_error(session, worker, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise RuntimeError("a bug")

    monkeypatch.setattr(worker_module, "search_batch", broken)
    run = await _new_run(session, "running")
    session.add(WorkspaceSearchCursor(run_id=run.id, source="arxiv", cursor_json={"value": 0}))
    await session.commit()
    run_id = run.id  # captured before the call: the worker's own rollback expires `run` (test_references_api.py's pattern)

    await worker_module.run_workspace_search(worker, str(run_id))

    reloaded = await session.get(WorkspaceSearchRun, run_id, populate_existing=True)
    assert reloaded.status == "failed"
