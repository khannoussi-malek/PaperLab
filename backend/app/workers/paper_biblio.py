"""ARQ job: a paper saved without its PDF gets the citation fields ingest would have given it (volume, issue, pages,
editors, PubMed ids), from Crossref by DOI and OpenAlex, as `enrichment.fill_biblio` does for an ingested PDF. Only
empty fields are filled and never a hand edit. Sources off in Settings → Paper sources are not asked. Never raises:
the paper is already usable without these fields. `ctx["transport"]` is a test hook."""

import logging
import uuid
from contextlib import AsyncExitStack

from app.core import enrichment, paper_sources
from app.db import SessionLocal
from app.models import Paper
from app.providers import crossref, openalex

logger = logging.getLogger(__name__)


async def fill_paper_biblio(ctx: dict, paper_id: str) -> None:
    pid = uuid.UUID(paper_id)
    transport = ctx.get("transport")
    async with SessionLocal() as session:
        if await session.get(Paper, pid) is None:
            return
        try:
            sources = await paper_sources.get(session)
            async with AsyncExitStack() as stack:
                cr = oa = None
                if sources.enabled["crossref"]:
                    cr = await stack.enter_async_context(
                        crossref.new_client(email=sources.contact_email, transport=transport)
                    )
                if sources.enabled["openalex"]:
                    oa = await stack.enter_async_context(
                        openalex.new_client(
                            email=sources.contact_email, transport=transport, api_key=sources.api_keys["openalex"]
                        )
                    )
                if cr or oa:
                    await enrichment.fill_biblio(session, pid, cr, oa)
        except Exception:
            logger.exception("filling the citation fields of %s failed; the paper stays usable", pid)
            await session.rollback()
