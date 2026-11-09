"""Snowball runs from before the snowball tree are named "snowball (1 seed paper(s))"; show their seed instead."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event

from app.core import search_run_results, workspace_search
from app.core.candidates import normal_title
from app.models import Paper
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

OLD = "snowball (1 seed paper(s))"


async def _run(session, ws, query, stats=None):
    run = WorkspaceSearchRun(
        workspace_id=ws.id, query_text=query, filters_json={}, query_overrides_json={}, sources_json=[],
        status="exhausted", started_at=datetime.now(timezone.utc), stats_json=stats or {},
    )
    session.add(run)
    await session.flush()
    return run


async def _seed_paper(session, title):
    paper = Paper(title=title, doi=f"10.5555/{uuid.uuid4().hex[:8]}", file_path="/x.pdf")
    session.add(paper)
    await session.flush()
    return paper


async def _hit(session, ws, run, seed=None):
    ref = ExternalRef(title="h")
    session.add(ref)
    await session.flush()
    session.add(WorkspaceSearchHit(
        workspace_id=ws.id, run_id=run.id, external_ref_id=ref.id, source_method="snowball_backward",
        seed_paper_id=seed.id if seed else None, normalized_title=normal_title(uuid.uuid4().hex),
        first_seen_at=datetime.now(timezone.utc),
    ))


async def _setup(session):
    ws = Workspace(name=f"labels-{uuid.uuid4().hex[:8]}")
    session.add(ws)
    await session.flush()
    return ws


async def test_old_run_with_paper_seed_names_it(session):
    ws = await _setup(session)
    run, two = await _run(session, ws, OLD), await _run(session, ws, OLD)
    a, b = await _seed_paper(session, "Alpha"), await _seed_paper(session, "Beta")
    await _hit(session, ws, run, a)
    await _hit(session, ws, run, a)
    await _hit(session, ws, two, a)
    await _hit(session, ws, two, b)
    await session.commit()
    labels = await search_run_results.run_labels(session, [run, two])
    assert labels[run.id] == 'Snowball from "Alpha"'
    assert labels[two.id] == 'Snowball from "Alpha" and 1 more'


async def test_old_run_without_seed_says_older_run(session):
    ws = await _setup(session)
    run = await _run(session, ws, OLD)
    await _hit(session, ws, run)
    await session.commit()
    assert (await search_run_results.run_labels(session, [run]))[run.id] == "Snowball (older run)"


async def test_new_and_keyword_runs_are_unchanged(session):
    ws = await _setup(session)
    new = await _run(session, ws, 'Snowball from "X"', {"snowball": {"seeds": [], "directions": []}})
    stale = await _run(session, ws, OLD, {"snowball": {"seeds": [], "directions": []}})
    kw = await _run(session, ws, "bert")
    await session.commit()
    labels = await search_run_results.run_labels(session, [new, stale, kw])
    assert labels == {new.id: new.query_text, stale.id: OLD, kw.id: "bert"}


async def test_summaries_use_label_and_one_query_for_many_old_runs(session):
    ws = await _setup(session)
    seed = await _seed_paper(session, "Gamma")
    runs = [await _run(session, ws, OLD) for _ in range(5)]
    for r in runs:
        await _hit(session, ws, r, seed)
    await session.commit()
    seen = []
    engine = session.bind.sync_engine if hasattr(session.bind, "sync_engine") else session.get_bind()
    listener = lambda conn, cur, stmt, *a: seen.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await search_run_results.run_labels(session, runs)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len([s for s in seen if s.startswith("SELECT")]) == 1
    summaries = await workspace_search.run_summaries(session, [(r, 1) for r in runs])
    assert {s.query_text for s in summaries} == {'Snowball from "Gamma"'}
    assert all(r.query_text == OLD for r in runs)  # stored value untouched
