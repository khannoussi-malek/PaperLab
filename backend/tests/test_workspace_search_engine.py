import uuid
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core import discovery
from app.core.candidates import normal_title
from app.core.paper_sources import SOURCES, SourceSettings
from app.core.workspace_search import search_batch
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import arxiv, discovery_fake

pytestmark = pytest.mark.anyio

# Task 2's cursor convention (task-2-brief.md): 0 for arXiv/CORE/Crossref/S2 (offset-style), 1 for OpenAlex
# (1-based page number). Starting OpenAlex at 0 would ask its fake for a negative offset and get nothing back.
START_CURSOR = {"arxiv": 0, "semantic_scholar": 0, "openalex": 1}


@pytest.fixture
async def fake_providers():
    """Every source on, routed to discovery_fake's real MockTransport — same pattern as test_discovery_fake.py's own
    `fake_providers` fixture. search_batch's merge/dedup then runs against the real fake provider (Task 11's
    PAGE_PAPERS fixture), not a hand-rolled mock of provider responses."""
    every_source = SourceSettings(contact_email=discovery_fake.MAILTO, enabled=dict.fromkeys(SOURCES, True))
    providers = discovery.build_providers(every_source, discovery_fake.transport())
    yield providers
    await providers.aclose()


async def _new_run(session, sources: list[str]) -> WorkspaceSearchRun:
    workspace = Workspace(name=f"Engine test {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id,
        query_text="bert",
        filters_json={},
        query_overrides_json={},
        sources_json=sources,
        status="running",
        started_at=datetime.now(timezone.utc),
        stats_json={},
    )
    session.add(run)
    await session.flush()
    for source in sources:
        session.add(WorkspaceSearchCursor(run_id=run.id, source=source, cursor_json={"value": START_CURSOR[source]}))
    await session.commit()
    return run


async def test_search_batch_creates_hits_and_advances_cursors(session, fake_providers):
    run = await _new_run(session, ["arxiv"])

    result = await search_batch(session, fake_providers, run)

    assert result.new_hits >= 1
    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id))).scalars().all()
    )
    assert len(hits) == result.new_hits
    assert all(h.acquisition_status == "not_attempted" for h in hits)

    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "arxiv"
            )
        )
    ).scalar_one()
    assert cursor.exhausted  # PAGE_SIZE_BY_SOURCE["arxiv"] (20) exceeds the fixture's 3-item page


async def test_search_batch_dedupes_across_sources(session, fake_providers):
    # discovery_fake's PAGE_PAPERS fixture answers the same 3 papers (shared DOIs) from every source; the merge
    # step (reusing candidates.merge/_same_paper) must collapse them to one hit per paper, not one per source.
    run = await _new_run(session, ["arxiv", "semantic_scholar", "openalex"])

    result = await search_batch(session, fake_providers, run)

    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id))).scalars().all()
    )
    titles = {h.normalized_title for h in hits}
    assert len(titles) == len(hits)  # no duplicate normalized titles from the same fixture paper
    assert len(hits) == 3  # 3 sources x 3 shared papers, merged down to 3 — not 9
    assert result.new_hits == 3


async def test_search_batch_preserves_existing_screening_state(session, fake_providers):
    # discovery_fake's PAGE_PAPERS[0] ("...Fixture 1", doi "...page-1") is what arxiv's page 0 returns first.
    # Pre-seed its ExternalRef + a WorkspaceSearchHit already screened by a user (this run's spec P2's global
    # constraint: a hit already in the pool — this run or an earlier one — keeps its screening state).
    run = await _new_run(session, ["arxiv"])
    title, doi = discovery_fake.PAGE_PAPERS[0]
    ref = ExternalRef(title=title, doi=doi)
    session.add(ref)
    await session.flush()
    existing_hit = WorkspaceSearchHit(
        workspace_id=run.workspace_id,
        run_id=run.id,
        external_ref_id=ref.id,
        source_method="database_search",
        normalized_title=normal_title(title),
        first_seen_at=datetime.now(timezone.utc),
        stage1_status="relevant",
        priority=2,
    )
    session.add(existing_hit)
    await session.commit()

    result = await search_batch(session, fake_providers, run)

    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.external_ref_id == ref.id)))
        .scalars()
        .all()
    )
    assert len(hits) == 1  # not duplicated by this batch
    assert hits[0].id == existing_hit.id
    assert hits[0].stage1_status == "relevant"  # untouched, not overwritten or reset
    assert hits[0].priority == 2
    assert result.new_hits == 2  # the other 2 PAGE_PAPERS are still new


async def test_search_batch_records_source_error_without_failing_run(session, fake_providers):
    broken_arxiv = arxiv.new_client(httpx.MockTransport(lambda request: httpx.Response(429)))
    providers = replace(fake_providers, arxiv=broken_arxiv)
    run = await _new_run(session, ["arxiv"])

    try:
        result = await search_batch(session, providers, run)
    finally:
        await broken_arxiv.aclose()

    assert "arxiv" in result.errors
    assert result.new_hits == 0
    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "arxiv"
            )
        )
    ).scalar_one()
    assert cursor.last_error is not None
    assert not cursor.exhausted


@pytest.mark.asyncio
async def test_start_run_creates_cursors_for_each_source(session):
    from app.core.workspace_search import start_run
    workspace = Workspace(name=f"Lifecycle {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()

    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv", "openalex"])

    assert run.status == "running"
    cursors = (await session.execute(
        select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    )).scalars().all()
    assert {c.source for c in cursors} == {"arxiv", "openalex"}


@pytest.mark.asyncio
async def test_stop_run_sets_status_and_stopped_at(session):
    from app.core.workspace_search import start_run, stop_run
    workspace = Workspace(name=f"Stop {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"])

    stopped = await stop_run(session, run.id)

    assert stopped.status == "stopped"
    assert stopped.stopped_at is not None


@pytest.mark.asyncio
async def test_start_run_on_a_stopped_run_resumes_its_cursors(session):
    from app.core.workspace_search import start_run, stop_run
    workspace = Workspace(name=f"Resume {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"])
    cursor = (await session.execute(
        select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    )).scalar_one()
    cursor.cursor_json = {"value": 40}
    await session.commit()
    await stop_run(session, run.id)

    resumed = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"], run_id=run.id)

    assert resumed.id == run.id
    assert resumed.status == "running"
    reloaded_cursor = (await session.execute(
        select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    )).scalar_one()
    assert reloaded_cursor.cursor_json == {"value": 40}
