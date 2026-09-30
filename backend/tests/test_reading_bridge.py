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


async def test_reading_queue_lists_only_stage_2_included_and_imported_papers(session):
    workspace = await workspaces.create(session, f"Queue {RUN}")
    run = await add_run(session, workspace.id)
    included_and_imported = await add_paper(session, title=f"Included {RUN}")
    await workspaces.add_paper(session, workspace.id, included_and_imported.id)
    await add_hit(session, workspace.id, run.id, included_and_imported.id, priority=1)
    await workspace_search.set_eligibility(session, workspace.id, included_and_imported.id, run.id, "include", None)

    excluded = await add_paper(session, title=f"Excluded {RUN}")
    await workspaces.add_paper(session, workspace.id, excluded.id)
    await add_hit(session, workspace.id, run.id, excluded.id, priority=2)
    await workspace_search.set_eligibility(session, workspace.id, excluded.id, run.id, "exclude", "wrong_topic")

    # Review Focus #2: included in stage 2 but never actually imported (no paper_id on the hit) — must not appear.
    await add_hit(session, workspace.id, run.id, None, priority=1)

    rows = await reading_bridge.reading_queue(session, workspace.id, run.id)

    assert [r.paper_id for r in rows] == [included_and_imported.id]


async def test_reading_queue_orders_by_priority_then_title(session):
    workspace = await workspaces.create(session, f"Order {RUN}")
    run = await add_run(session, workspace.id)
    for title, priority in [("Z low priority", 3), ("A high priority", 1), ("B also high", 1)]:
        paper = await add_paper(session, title=f"{title} {RUN}")
        await workspaces.add_paper(session, workspace.id, paper.id)
        await add_hit(session, workspace.id, run.id, paper.id, priority=priority)
        await workspace_search.set_eligibility(session, workspace.id, paper.id, run.id, "include", None)

    rows = await reading_bridge.reading_queue(session, workspace.id, run.id)

    assert [r.title.split(" ", 1)[0] for r in rows] == ["A", "B", "Z"]  # priority 1s before priority 3, A before B


async def test_reading_queue_shows_not_started_as_pass_zero_no_triage(session):
    """Review Focus #5: a never-opened included paper is a normal state, not a gap."""
    workspace = await workspaces.create(session, f"Fresh {RUN}")
    run = await add_run(session, workspace.id)
    paper = await add_paper(session, title=f"Fresh paper {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    await add_hit(session, workspace.id, run.id, paper.id, priority=1)
    await workspace_search.set_eligibility(session, workspace.id, paper.id, run.id, "include", None)

    [row] = await reading_bridge.reading_queue(session, workspace.id, run.id)

    assert (row.reading_pass, row.triage, row.note_count) == (0, None, 0)


async def test_reading_queue_route_200s_with_the_right_rows(session, client):
    workspace = await workspaces.create(session, f"RouteQ {RUN}")
    run = await add_run(session, workspace.id)
    paper = await add_paper(session, title=f"Routed {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    await add_hit(session, workspace.id, run.id, paper.id, priority=1)
    await workspace_search.set_eligibility(session, workspace.id, paper.id, run.id, "include", None)

    response = await client.get(f"/api/workspaces/{workspace.id}/search/reading-queue?run={run.id}")

    assert response.status_code == 200
    [row] = response.json()["rows"]
    assert row["paper_id"] == str(paper.id)


async def test_reading_queue_route_404s_for_a_run_from_another_workspace(session, client):
    workspace = await workspaces.create(session, f"Wrong {RUN}")
    other = await workspaces.create(session, f"Other {RUN}")
    run = await add_run(session, other.id)

    response = await client.get(f"/api/workspaces/{workspace.id}/search/reading-queue?run={run.id}")

    assert response.status_code == 404


async def test_reading_queue_dedupes_a_paper_with_two_hits_in_the_same_run(session):
    """import_hits's own docstring names the real scenario: a second ExternalRef's hit gets attached to a paper
    already imported via an earlier hit in the same run, leaving two WorkspaceSearchHit rows for one paper. The
    queue must still show that paper once, keeping the most urgent (lowest) priority across its hits."""
    workspace = await workspaces.create(session, f"Dup {RUN}")
    run = await add_run(session, workspace.id)
    paper = await add_paper(session, title=f"Dup paper {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    await add_hit(session, workspace.id, run.id, paper.id, priority=5)
    await add_hit(session, workspace.id, run.id, paper.id, priority=2)
    await workspace_search.set_eligibility(session, workspace.id, paper.id, run.id, "include", None)

    rows = await reading_bridge.reading_queue(session, workspace.id, run.id)

    assert [(r.paper_id, r.priority) for r in rows] == [(paper.id, 2)]


async def test_reading_queue_dedupes_null_and_set_priority_on_the_same_paper(session):
    """MIN() ignores NULLs in SQL — a paper with one hit lacking a priority and another hit with priority=3
    must show priority 3, not NULL, not the dropped hit."""
    workspace = await workspaces.create(session, f"MixedPrio {RUN}")
    run = await add_run(session, workspace.id)
    paper = await add_paper(session, title=f"Mixed priority {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    await add_hit(session, workspace.id, run.id, paper.id, priority=None)
    await add_hit(session, workspace.id, run.id, paper.id, priority=3)
    await workspace_search.set_eligibility(session, workspace.id, paper.id, run.id, "include", None)

    rows = await reading_bridge.reading_queue(session, workspace.id, run.id)

    assert [(r.paper_id, r.priority) for r in rows] == [(paper.id, 3)]


async def test_reading_queue_sorts_null_priority_after_any_set_priority(session):
    """nulls_last() is asserted in the query but needs a paper with no priority alongside one that has it to
    actually exercise the ordering."""
    workspace = await workspaces.create(session, f"NullPrio {RUN}")
    run = await add_run(session, workspace.id)
    no_priority = await add_paper(session, title=f"No priority {RUN}")
    await workspaces.add_paper(session, workspace.id, no_priority.id)
    await add_hit(session, workspace.id, run.id, no_priority.id, priority=None)
    await workspace_search.set_eligibility(session, workspace.id, no_priority.id, run.id, "include", None)

    has_priority = await add_paper(session, title=f"Has priority {RUN}")
    await workspaces.add_paper(session, workspace.id, has_priority.id)
    await add_hit(session, workspace.id, run.id, has_priority.id, priority=5)
    await workspace_search.set_eligibility(session, workspace.id, has_priority.id, run.id, "include", None)

    rows = await reading_bridge.reading_queue(session, workspace.id, run.id)

    assert [r.paper_id for r in rows] == [has_priority.id, no_priority.id]


async def test_reading_queue_is_empty_for_a_run_with_no_included_papers(session):
    workspace = await workspaces.create(session, f"Empty {RUN}")
    run = await add_run(session, workspace.id)

    assert await reading_bridge.reading_queue(session, workspace.id, run.id) == []
