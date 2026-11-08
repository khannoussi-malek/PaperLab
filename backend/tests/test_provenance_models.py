import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models.paper import Paper
from app.models.provenance import BACKFILL_SQL, WorkspaceBranchState, WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

pytestmark = pytest.mark.anyio


async def _workspace_and_run(session):
    workspace = Workspace(name=f"prov-{uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", sources_json=["arxiv"], status="exhausted",
        started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    return workspace, run


async def _hit(session, workspace, run, method, *, seed=None, paper=None, age=0):
    ref = ExternalRef(title=f"t-{uuid.uuid4().hex}")
    session.add(ref)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method=method,
        seed_paper_id=seed, paper_id=paper, normalized_title=uuid.uuid4().hex,
        first_seen_at=datetime.now(timezone.utc) - timedelta(minutes=age),
    )
    session.add(hit)
    await session.flush()
    return hit


async def _paper(session):
    paper = Paper(title=f"p-{uuid.uuid4().hex}")
    session.add(paper)
    await session.flush()
    return paper


async def _backfill(session):
    for statement in BACKFILL_SQL:
        await session.execute(text(statement))


async def _links(session, workspace):
    result = await session.execute(select(WorkspaceHitLink).where(WorkspaceHitLink.workspace_id == workspace.id))
    return result.scalars().all()


async def test_link_unique_per_path(session):
    workspace, run = await _workspace_and_run(session)
    hit = await _hit(session, workspace, run, "database_search")
    for _ in range(2):
        session.add(WorkspaceHitLink(workspace_id=workspace.id, child_hit_id=hit.id, run_id=run.id, kind="search"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_branch_state_needs_exactly_one_target(session):
    workspace, run = await _workspace_and_run(session)
    hit = await _hit(session, workspace, run, "database_search")
    paper = await _paper(session)
    for kwargs in ({"hit_id": hit.id, "paper_id": paper.id}, {}):
        async with session.begin_nested():
            session.add(WorkspaceBranchState(workspace_id=workspace.id, state="stopped", **kwargs))
            with pytest.raises(IntegrityError):
                await session.flush()


async def _seed_four(session):
    workspace, run = await _workspace_and_run(session)
    paper_p, paper_q = await _paper(session), await _paper(session)
    search = await _hit(session, workspace, run, "database_search")
    older = await _hit(session, workspace, run, "database_search", paper=paper_p.id, age=10)
    await _hit(session, workspace, run, "database_search", paper=paper_p.id, age=1)  # later duplicate of P
    back = await _hit(session, workspace, run, "snowball_backward", seed=paper_p.id)
    fwd = await _hit(session, workspace, run, "snowball_forward", seed=paper_q.id)
    orphan = await _hit(session, workspace, run, "snowball_backward")
    return workspace, run, search, older, back, fwd, orphan, paper_q


async def test_backfill_links_old_hits(session):
    workspace, run, search, older, back, fwd, orphan, paper_q = await _seed_four(session)
    await _backfill(session)
    by_child = {link.child_hit_id: link for link in await _links(session, workspace)}
    assert by_child[search.id].kind == "search" and by_child[search.id].run_id == run.id
    assert by_child[back.id].kind == "cites" and by_child[back.id].parent_hit_id == older.id
    assert by_child[fwd.id].kind == "cited_by" and by_child[fwd.id].parent_paper_id == paper_q.id
    assert by_child[fwd.id].parent_hit_id is None
    assert orphan.id not in by_child


async def test_backfill_is_idempotent(session):
    workspace, *_ = await _seed_four(session)
    await _backfill(session)
    first = len(await _links(session, workspace))
    await _backfill(session)
    assert len(await _links(session, workspace)) == first
