"""Seeds a workspace hit pool for M31's tests: one ExternalRef per hit, its text as the abstract."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


async def make_pool(session, rows: list[tuple[str, str | None]]) -> tuple[Workspace, list[WorkspaceSearchHit]]:
    """`rows`: (abstract, stage1_status) in found order. A decided hit's stage1_decided_at follows the same order,
    so the last decided row is the newest decision."""
    workspace = Workspace(name=f"Screening {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", filters_json={}, query_overrides_json={},
        sources_json=["arxiv"], status="exhausted", started_at=BASE, stats_json={},
    )
    session.add(run)
    await session.flush()
    hits = []
    for index, (abstract, status) in enumerate(rows):
        ref = ExternalRef(title=f"paper {index}", abstract=abstract)
        session.add(ref)
        await session.flush()
        hit = WorkspaceSearchHit(
            workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method="database_search",
            normalized_title=f"paper {index}", first_seen_at=BASE + timedelta(seconds=index),
            stage1_status=status, stage1_exclude_reason="wrong_topic" if status == "not_relevant" else None,
            stage1_decided_at=BASE + timedelta(hours=1, seconds=index) if status else None,
        )
        session.add(hit)
        hits.append(hit)
    await session.flush()
    return workspace, hits
