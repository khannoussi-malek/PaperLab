"""Settings → Paper sources: which sources Find papers and Similar ask, their API keys and the contact email. No
response has a key."""

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import paper_sources
from app.schemas.paper_sources import PaperSourcesOut, PaperSourcesUpdate

router = APIRouter(prefix="/api/paper-sources", tags=["paper-sources"])


@router.get("")
async def get_paper_sources(session: SessionDep) -> PaperSourcesOut:
    return paper_sources.view(await paper_sources.get(session))


@router.patch("")
async def update_paper_sources(payload: PaperSourcesUpdate, session: SessionDep) -> PaperSourcesOut:
    """Only what's sent changes. 422 for a malformed email, an empty key, or a key for a source that takes none."""
    changes: dict = {}
    if "contact_email" in payload.model_fields_set:
        changes["contact_email"] = payload.contact_email
    if payload.enabled is not None:
        changes["enabled"] = {source: getattr(payload.enabled, source) for source in payload.enabled.model_fields_set}
    if payload.api_keys is not None:
        keys = {source: getattr(payload.api_keys, source) for source in payload.api_keys.model_fields_set}
        changes["api_keys"] = {source: key and key.get_secret_value() for source, key in keys.items()}
    return paper_sources.view(await paper_sources.update(session, changes))
