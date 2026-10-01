"""Read-only endpoints connecting M30's search/screening feature to M21's reading-progress feature (spec §12)."""

import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import papers, reading_bridge
from app.schemas.reading_bridge import ReadingContextListOut, ReadingContextOut, ReadingQueueOut, ReadingQueueRowOut

router = APIRouter(prefix="/api/papers", tags=["reading-bridge"])


@router.get("/{paper_id}/reading-context")
async def get_reading_context(paper_id: uuid.UUID, session: SessionDep) -> ReadingContextListOut:
    """404 for an unknown paper; an empty list (200) for a real paper never pulled into a search."""
    await papers.get_paper(session, paper_id)  # raises NotFound for an unknown id; the return value is unused
    contexts = await reading_bridge.reading_context(session, paper_id)
    return ReadingContextListOut(contexts=[ReadingContextOut(**vars(c)) for c in contexts])


# A second router, not a second prefix on `router`: APIRouter takes exactly one `prefix`, so a route under
# /api/workspaces needs its own instance, registered separately in main.py alongside `router` above.
workspace_router = APIRouter(prefix="/api/workspaces", tags=["reading-bridge"])


@workspace_router.get("/{workspace_id}/search/reading-queue")
async def get_reading_queue(workspace_id: uuid.UUID, run: uuid.UUID, session: SessionDep) -> ReadingQueueOut:
    rows = await reading_bridge.reading_queue(session, workspace_id, run)
    return ReadingQueueOut(rows=[ReadingQueueRowOut(**vars(r)) for r in rows])
