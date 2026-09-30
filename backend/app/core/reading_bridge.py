"""Connects M30's search/screening feature to M21's reading-progress feature: why a paper was pulled into a
survey, and how far the survey has actually been read (spec §12). Read-only — no new table, no new write path."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_search import get_run
from app.models import Paper, Workspace, note_papers
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


@dataclass(frozen=True)
class ReadingQueueRow:
    paper_id: uuid.UUID
    title: str
    priority: int | None
    reading_pass: int
    triage: str | None
    note_count: int


async def reading_queue(session: AsyncSession, workspace_id: uuid.UUID, run_id: uuid.UUID) -> list[ReadingQueueRow]:
    """Every stage-2-included, already-imported paper for this run (Review Focus #2: excludes an included hit with
    no paper_id yet — that's still acquisition, not reading), with its reading progress and note count."""
    await get_run(session, run_id, workspace_id)
    note_count = (
        select(func.count(func.distinct(note_papers.c.note_id)))
        .where(note_papers.c.paper_id == Paper.id)
        .correlate(Paper)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(
                Paper.id,
                Paper.title,
                WorkspaceSearchHit.priority,
                Paper.reading_pass,
                Paper.triage,
                note_count.label("note_count"),
            )
            .select_from(SearchRunEligibility)
            .join(
                WorkspaceSearchHit,
                (WorkspaceSearchHit.paper_id == SearchRunEligibility.paper_id)
                & (WorkspaceSearchHit.run_id == SearchRunEligibility.search_run_id),
            )
            .join(Paper, Paper.id == SearchRunEligibility.paper_id)
            .where(
                SearchRunEligibility.search_run_id == run_id,
                WorkspaceSearchHit.workspace_id == workspace_id,
                SearchRunEligibility.stage2_status == "include",
                WorkspaceSearchHit.paper_id.is_not(None),
            )
            .order_by(WorkspaceSearchHit.priority.asc().nulls_last(), Paper.title)
        )
    ).all()
    return [
        ReadingQueueRow(paper_id=r[0], title=r[1], priority=r[2], reading_pass=r[3], triage=r[4], note_count=r[5])
        for r in rows
    ]
