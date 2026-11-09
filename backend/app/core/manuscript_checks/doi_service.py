"""Glue for "Check DOIs online": read the manuscript, ask Crossref about each .bib DOI (S2P B2).
Only the DOIs go out."""

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import paper_sources
from app.core.errors import InvalidInput
from app.core.manuscript_checks import service
from app.core.manuscript_checks.references_doi import DEADLINE_SECONDS, DoiCheckResult, check_dois, doi_entries
from app.providers import crossref

new_client = crossref.new_client  # tests replace this with a client on a mock transport


async def run_doi_check(session: AsyncSession, mid: uuid.UUID) -> DoiCheckResult:
    ctx = await service.load_context(session, mid)  # NotFound("unknown_manuscript")
    sources = await paper_sources.get(session)  # only the on/off switch is read, never the contact email
    if not sources.enabled["crossref"]:
        raise InvalidInput("crossref_disabled")  # the owner turned Crossref off: send nothing
    entries = doi_entries(ctx.files)
    if not entries:
        return DoiCheckResult(0, 0, [])
    async with new_client(email=None) as http:  # DOIs only: no contact email, so the public (slower) Crossref pool
        return await check_dois(entries, lambda doi: crossref.get_work(http, doi),
                                deadline=time.monotonic() + DEADLINE_SECONDS)
