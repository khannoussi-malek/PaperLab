"""The reading bridge: why a paper was pulled into a search, and how far its survey has been read (M30 §12)."""

import uuid
from datetime import datetime, timezone

import pytest

from app.core import reading_bridge, workspace_search, workspaces
from app.models import Paper
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]


async def add_paper(session, **fields) -> Paper:
    paper = Paper(**{"file_path": "/x.pdf", "title": f"Bridge {RUN}", **fields})
    session.add(paper)
    await session.flush()
    return paper


async def add_run(session, workspace_id) -> WorkspaceSearchRun:
    """Field names and required columns verified against `test_workspace_search_engine.py`'s own `_new_run`
    helper — `query_text`/`filters_json`, not `query`/`filters`, and `sources_json`/`started_at`/`stats_json` have
    no default at the Python level and must be set explicitly."""
    run = WorkspaceSearchRun(
        workspace_id=workspace_id,
        query_text=f"q {RUN}",
        filters_json={},
        query_overrides_json={},
        sources_json=[],
        status="stopped",
        started_at=datetime.now(timezone.utc),
        stats_json={},
    )
    session.add(run)
    await session.flush()
    return run


async def add_hit(session, workspace_id, run_id, paper_id, *, priority=None, note=None) -> WorkspaceSearchHit:
    """`first_seen_at` has no default at the Python level either — set it explicitly, per the same existing
    helper's own pattern."""
    hit = WorkspaceSearchHit(
        workspace_id=workspace_id,
        run_id=run_id,
        normalized_title=f"bridge {RUN}",
        source_method="database_search",
        first_seen_at=datetime.now(timezone.utc),
        stage1_status="relevant",
        priority=priority,
        stage1_note=note,
        acquisition_status="imported",
        paper_id=paper_id,
    )
    session.add(hit)
    await session.flush()
    return hit


async def test_a_paper_with_no_hits_has_no_reading_context(session):
    paper = await add_paper(session)

    assert await reading_bridge.reading_context(session, paper.id) == []


async def test_a_papers_reading_context_names_the_workspace_priority_and_note(session):
    paper = await add_paper(session)
    workspace = await workspaces.create(session, f"Survey {RUN}")
    run = await add_run(session, workspace.id)
    await add_hit(session, workspace.id, run.id, paper.id, priority=2, note="Core method paper")

    [context] = await reading_bridge.reading_context(session, paper.id)

    assert (context.workspace_id, context.workspace_name, context.priority, context.note) == (
        workspace.id,
        f"Survey {RUN}",
        2,
        "Core method paper",
    )
    assert context.stage2_status is None  # no eligibility verdict recorded yet


async def test_a_papers_reading_context_lists_every_workspace_it_was_found_in(session):
    """Review Focus #1: two workspaces, both must show, not just one."""
    paper = await add_paper(session)
    ws_a = await workspaces.create(session, f"A {RUN}")
    ws_b = await workspaces.create(session, f"B {RUN}")
    run_a = await add_run(session, ws_a.id)
    run_b = await add_run(session, ws_b.id)
    await add_hit(session, ws_a.id, run_a.id, paper.id, priority=1)
    await add_hit(session, ws_b.id, run_b.id, paper.id, priority=3)

    contexts = await reading_bridge.reading_context(session, paper.id)

    assert {c.workspace_id for c in contexts} == {ws_a.id, ws_b.id}


async def test_a_papers_reading_context_includes_the_stage_2_verdict_when_one_exists(session):
    paper = await add_paper(session)
    workspace = await workspaces.create(session, f"Survey2 {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    run = await add_run(session, workspace.id)
    await add_hit(session, workspace.id, run.id, paper.id, priority=1)
    await workspace_search.set_eligibility(session, workspace.id, paper.id, run.id, "include", None)

    [context] = await reading_bridge.reading_context(session, paper.id)

    assert context.stage2_status == "include"


async def test_reading_context_route_returns_empty_for_a_paper_with_no_hits(session, client):
    paper = await add_paper(session)

    response = await client.get(f"/api/papers/{paper.id}/reading-context")

    assert (response.status_code, response.json()) == (200, {"contexts": []})


async def test_reading_context_route_404s_for_an_unknown_paper(client):
    response = await client.get(f"/api/papers/{uuid.uuid4()}/reading-context")

    assert response.status_code == 404
