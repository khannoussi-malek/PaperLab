"""R21: what happened to a paper (a free PDF found by the re-check, a PDF attached), and the Found PDFs notice."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, PaperEvent


async def record(session: AsyncSession, paper_id: uuid.UUID, kind: str, detail: dict[str, Any]) -> PaperEvent:
    event = PaperEvent(paper_id=paper_id, kind=kind, detail=detail)
    session.add(event)
    await session.commit()
    return event


async def history(session: AsyncSession, paper_id: uuid.UUID) -> list[PaperEvent]:
    """Newest first."""
    query = select(PaperEvent).where(PaperEvent.paper_id == paper_id)
    return list(await session.scalars(query.order_by(PaperEvent.created_at.desc(), PaperEvent.id.desc())))


async def unseen_found(session: AsyncSession) -> list[tuple[PaperEvent, str]]:
    """The re-check's finds the owner hasn't dismissed, with the paper's title, newest first."""
    query = (
        select(PaperEvent, Paper.title)
        .join(Paper, Paper.id == PaperEvent.paper_id)
        .where(PaperEvent.kind == "pdf_found", PaperEvent.seen_at.is_(None))
        .order_by(PaperEvent.created_at.desc(), PaperEvent.id.desc())
    )
    return [(event, title) for event, title in (await session.execute(query)).all()]


async def mark_seen(session: AsyncSession, ids: list[uuid.UUID]) -> None:
    """Only the finds the owner was shown: one that arrived after the list was fetched stays unseen."""
    await session.execute(
        update(PaperEvent)
        .where(PaperEvent.id.in_(ids), PaperEvent.kind == "pdf_found", PaperEvent.seen_at.is_(None))
        .values(seen_at=datetime.now(timezone.utc))
    )
    await session.commit()
