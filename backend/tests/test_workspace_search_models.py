import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchRun, WorkspaceSearchCursor, WorkspaceSearchHit

pytestmark = pytest.mark.anyio


async def test_run_cursor_hit_round_trip(session):
    workspace = Workspace(name=f"Search models {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()

    run = WorkspaceSearchRun(
        workspace_id=workspace.id,
        query_text="large language model code review",
        filters_json={},
        query_overrides_json={},
        sources_json=["arxiv", "semantic_scholar"],
        status="running",
        started_at=datetime.now(timezone.utc),
        stats_json={},
    )
    session.add(run)
    await session.flush()

    cursor = WorkspaceSearchCursor(run_id=run.id, source="arxiv", cursor_json={"start": 0})
    session.add(cursor)

    hit = WorkspaceSearchHit(
        workspace_id=workspace.id,
        run_id=run.id,
        source_method="database_search",
        normalized_title="a paper about code review",
        first_seen_at=datetime.now(timezone.utc),
    )
    session.add(hit)
    await session.commit()

    # Scoped to this test's own row: this suite shares the dev database (conftest.py), which now holds
    # thousands of real hits from manual testing — an unfiltered select(WorkspaceSearchHit) finds all of them,
    # not just this one, and .scalar_one() correctly refuses to pick a row among many.
    loaded = (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.id == hit.id))).scalar_one()
    assert loaded.acquisition_status == "not_attempted"
    assert loaded.run_id == run.id


async def test_hit_unique_per_workspace_and_external_ref(session):
    from app.models.references import ExternalRef

    workspace = Workspace(name=f"Search dedup {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    ref = ExternalRef(title="Attention Is All You Need", s2_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776")
    session.add(ref)
    await session.flush()

    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", filters_json={}, query_overrides_json={},
        sources_json=[], status="running", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()

    session.add(WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id,
        source_method="database_search", normalized_title="attention is all you need",
        first_seen_at=datetime.now(timezone.utc),
    ))
    await session.commit()

    session.add(WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id,
        source_method="database_search", normalized_title="attention is all you need",
        first_seen_at=datetime.now(timezone.utc),
    ))
    with pytest.raises(Exception):  # IntegrityError — driver-specific, caught broadly here
        await session.commit()
    await session.rollback()
