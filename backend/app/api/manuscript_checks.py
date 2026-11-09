import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import manuscripts
from app.core.manuscript_checks import service
from app.core.manuscript_checks.registry import REGISTRY
from app.schemas.manuscript_checks import CheckInfoOut, CheckFindingOut, RunChecksIn, RunChecksOut

router = APIRouter(tags=["manuscripts"])
BASE = "/api/manuscripts/{manuscript_id}/checks"


@router.get(BASE)
async def list_checks(manuscript_id: uuid.UUID, session: SessionDep) -> list[CheckInfoOut]:
    await manuscripts.get(session, manuscript_id)
    return [CheckInfoOut(name=c.name, cost=c.cost, description=c.description) for c in REGISTRY]


@router.post(BASE + "/run")
async def run_checks(manuscript_id: uuid.UUID, body: RunChecksIn, session: SessionDep) -> RunChecksOut:
    run = await service.run_checks(session, manuscript_id, body.names, body.cost)
    return RunChecksOut(ran=run.ran, counts=run.counts, findings=[CheckFindingOut(**vars(f)) for f in run.findings])
