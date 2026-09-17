"""The reader's References tab: a paper's references and citing works, a refresh, and importing one (M7.5)."""

import uuid

from fastapi import APIRouter, Request

from app.api.deps import DiscoveryDep, SessionDep
from app.config import settings
from app.core import references, workspaces
from app.schemas.papers import PaperOut
from app.schemas.references import Direction, ImportReferenceIn, ReferencesOut, RefreshOut

router = APIRouter(tags=["references"])


@router.get("/api/papers/{paper_id}/references")
async def list_references(paper_id: uuid.UUID, session: SessionDep, direction: Direction = "cites") -> ReferencesOut:
    """Ranked for this library. `state` is `none` until a fetch is asked for, `fetching` while the worker runs."""
    return await references.listing(session, paper_id, direction)


@router.post("/api/papers/{paper_id}/references/refresh", status_code=202)
async def refresh_references(paper_id: uuid.UUID, request: Request, session: SessionDep) -> RefreshOut:
    """Queues a fetch of both directions. A second call while a recent fetch runs queues nothing. 404 unknown paper."""
    if await references.request_fetch(session, paper_id):
        await request.app.state.arq.enqueue_job("fetch_references", str(paper_id))
    return RefreshOut(state="fetching")


@router.post("/api/references/{ref_id}/import", status_code=201)
async def import_reference(
    ref_id: uuid.UUID, payload: ImportReferenceIn, request: Request, session: SessionDep, providers: DiscoveryDep
) -> PaperOut:
    """Downloads the reference's first free PDF and ingests it like an upload (D84). 404 for an unknown reference or
    workspace (before any download); 409 when the library already holds it or no free PDF is found."""
    if payload.workspace_id is not None:
        await workspaces.get(session, payload.workspace_id)
    paper = await references.import_reference(session, providers, ref_id, settings.pdf_dir)
    if payload.workspace_id is not None:
        await workspaces.add_paper(session, payload.workspace_id, paper.id)
    await request.app.state.arq.enqueue_job("ingest_paper", str(paper.id))
    return paper
