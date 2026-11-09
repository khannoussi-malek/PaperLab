import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.manuscript_checks import doi_service
from app.core.manuscript_checks.base import SEVERITIES
from app.schemas.manuscript_checks import CheckFindingOut
from app.schemas.manuscript_doi_check import DoiCheckOut

router = APIRouter(tags=["manuscripts"])


@router.post("/api/manuscripts/{manuscript_id}/checks/dois")
async def check_dois_online(manuscript_id: uuid.UUID, session: SessionDep) -> DoiCheckOut:
    result = await doi_service.run_doi_check(session, manuscript_id)
    counts = {s: sum(f.severity == s for f in result.findings) for s in SEVERITIES}
    return DoiCheckOut(checked=result.checked, not_checked=result.not_checked,
                       findings=[CheckFindingOut(**vars(f)) for f in result.findings], counts=counts)
