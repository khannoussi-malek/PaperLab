import uuid

from fastapi import APIRouter, Request

from app.api.deps import SessionDep
from app.core import workspace_search
from app.schemas.workspace_search import SearchRunCreate, SearchRunOut

router = APIRouter(prefix="/api/workspaces/{workspace_id}/search", tags=["workspace-search"])


async def _enqueue(request: Request, run_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("run_workspace_search", str(run_id))


@router.post("/runs", status_code=201)
async def start_run(
    workspace_id: uuid.UUID, payload: SearchRunCreate, session: SessionDep, request: Request
) -> SearchRunOut:
    run = await workspace_search.start_run(
        session, workspace_id, payload.query, payload.filters, payload.sources, payload.query_overrides,
    )
    await _enqueue(request, run.id)
    return run


@router.post("/runs/{run_id}")
async def restart_run(
    workspace_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep, request: Request
) -> SearchRunOut:
    run = await workspace_search.get_run(session, run_id)
    resumed = await workspace_search.start_run(
        session, workspace_id, run.query_text, run.filters_json, run.sources_json,
        run.query_overrides_json, run_id=run_id,
    )
    await _enqueue(request, run_id)
    return resumed


@router.post("/runs/{run_id}/stop")
async def stop_run(workspace_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep) -> SearchRunOut:
    return await workspace_search.stop_run(session, run_id, workspace_id=workspace_id)


@router.get("/runs/{run_id}")
async def get_run(workspace_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep) -> SearchRunOut:
    return await workspace_search.get_run(session, run_id, workspace_id=workspace_id)
