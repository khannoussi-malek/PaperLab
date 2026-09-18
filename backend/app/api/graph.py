"""The graph page's one request: every library paper and the links between them (D109)."""

import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import graph
from app.schemas.graph import GraphOut

router = APIRouter(tags=["graph"])


@router.get("/api/graph")
async def library_graph(session: SessionDep, workspace: uuid.UUID | None = None) -> GraphOut:
    """The whole library, or one workspace's papers and the links between them. 404 for an unknown workspace.
    Capped at graph.MAX_LINKS links, with `truncated` saying whether any were dropped."""
    return await graph.library_graph(session, workspace)
