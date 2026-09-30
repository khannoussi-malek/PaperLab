"""Connects M30's search/screening feature to M21's reading-progress feature: why a paper was pulled into a
survey, and how far the survey has actually been read (spec §12). Read-only — no new table, no new write path."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workspace
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit


@dataclass(frozen=True)
class ReadingContext:
    workspace_id: uuid.UUID
    workspace_name: str
    priority: int | None
    note: str | None
    stage2_status: str | None


async def reading_context(session: AsyncSession, paper_id: uuid.UUID) -> list[ReadingContext]:
    """Every workspace this paper has a search hit in (Review Focus #1: never just one), newest first. A paper
    never pulled in through a systematic search returns an empty list — the common case, not an error."""
    rows = (
        await session.execute(
            select(
                Workspace.id,
                Workspace.name,
                WorkspaceSearchHit.priority,
                WorkspaceSearchHit.stage1_note,
                SearchRunEligibility.stage2_status,
            )
            .select_from(WorkspaceSearchHit)
            .join(Workspace, Workspace.id == WorkspaceSearchHit.workspace_id)
            .join(
                SearchRunEligibility,
                (SearchRunEligibility.paper_id == WorkspaceSearchHit.paper_id)
                & (SearchRunEligibility.search_run_id == WorkspaceSearchHit.run_id),
                isouter=True,
            )
            .where(WorkspaceSearchHit.paper_id == paper_id)
            .order_by(WorkspaceSearchHit.first_seen_at.desc())
        )
    ).all()
    return [
        ReadingContext(workspace_id=r[0], workspace_name=r[1], priority=r[2], note=r[3], stage2_status=r[4])
        for r in rows
    ]
