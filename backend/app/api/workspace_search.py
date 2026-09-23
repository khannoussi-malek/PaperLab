import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, UploadFile

from app.api.deps import DiscoveryDep, SessionDep
from app.core import workspace_search
from app.schemas.workspace_search import (
    BulkHitReviewUpdate,
    BulkUpdateOut,
    HitListOut,
    HitOut,
    HitReviewUpdate,
    ImportHitsOut,
    ImportHitsRequest,
    SearchRunCreate,
    SearchRunOut,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/search", tags=["workspace-search"])


async def _enqueue(request: Request, run_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("run_workspace_search", str(run_id))


async def _enqueue_ingest(request: Request, paper_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("ingest_paper", str(paper_id))


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


@router.get("/hits")
async def list_hits(
    workspace_id: uuid.UUID, session: SessionDep, limit: Annotated[int, Query(gt=0)] = 50,
    after: str | None = None, stage1_status: str | None = None,
) -> HitListOut:
    items, next_cursor = await workspace_search.list_hits(session, workspace_id, limit, after, stage1_status)
    return HitListOut(items=items, next_cursor=next_cursor)


# Registered before "/hits/{hit_id}": both are PATCH routes and Starlette matches path templates in registration
# order, so "/hits/bulk" must come first or a PATCH to it would be swallowed by "/hits/{hit_id}" (and fail there
# trying to parse "bulk" as a UUID).
@router.patch("/hits/bulk")
async def patch_hits_bulk(workspace_id: uuid.UUID, payload: BulkHitReviewUpdate, session: SessionDep) -> BulkUpdateOut:
    count = await workspace_search.bulk_review_hits(
        session, workspace_id, payload.hit_ids, payload.stage1_status, payload.stage1_exclude_reason, payload.priority,
    )
    return BulkUpdateOut(updated=count)


@router.patch("/hits/{hit_id}")
async def patch_hit(
    workspace_id: uuid.UUID, hit_id: uuid.UUID, payload: HitReviewUpdate, session: SessionDep
) -> HitOut:
    return await workspace_search.review_hit(session, hit_id, workspace_id, payload)


@router.post("/hits/import")
async def import_hits(
    workspace_id: uuid.UUID, payload: ImportHitsRequest, session: SessionDep, providers: DiscoveryDep, request: Request
) -> ImportHitsOut:
    result = await workspace_search.import_hits(session, providers, workspace_id, payload.hit_ids)
    for paper_id in result.paper_ids:
        await _enqueue_ingest(request, paper_id)
    return ImportHitsOut(imported=result.imported, failed=result.failed)


@router.post("/hits/{hit_id}/upload")
async def upload_hit_pdf(
    workspace_id: uuid.UUID, hit_id: uuid.UUID, session: SessionDep, request: Request,
    file: UploadFile = File(...),
) -> HitOut:
    content = await file.read()
    hit, created = await workspace_search.upload_hit_pdf(session, workspace_id, hit_id, file.filename, content)
    if created:
        await _enqueue_ingest(request, hit.paper_id)
    return hit
