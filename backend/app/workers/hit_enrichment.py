"""ARQ job: enrich_hits (M59), the free-source backfill of triage data and missing abstracts (D283: Semantic Scholar
and arXiv, each only when it is on in Settings). Pre-screening runs it first."""

import logging
import uuid
from dataclasses import replace

from app.config import settings
from app.core import hit_enrichment, paper_sources
from app.db import SessionLocal
from app.providers import arxiv, discovery_fake, semantic_scholar

logger = logging.getLogger(__name__)

ENRICH_JOB_TIMEOUT = 3600


async def _arxiv_fallback(session, refs, transport) -> hit_enrichment.ArxivResult:
    if transport is None and settings.discovery_provider == "fake":
        transport = discovery_fake.transport()
    async with arxiv.new_client(transport=transport) as http:
        return await hit_enrichment.arxiv_abstracts(session, http, refs)


async def enrich_hits(ctx: dict, workspace_id: str, run_id: str | None = None) -> None:
    """Never raises for S2 or arXiv trouble: a rate-limited or failing chunk ends up in the logged result.
    ctx["transport"] and ctx["arxiv_transport"] are a test's MockTransports."""
    async with SessionLocal() as session:
        sources = await paper_sources.get(session)
        transport = ctx.get("transport")
        if transport is None and settings.discovery_provider == "fake":
            transport = discovery_fake.transport()
        ws, run = uuid.UUID(workspace_id), uuid.UUID(run_id) if run_id else None
        # Before filling too: once a citation is replaced, nothing shows a verdict was reached on it.
        cleared = await hit_enrichment.clear_stale_no_abstract(session, ws)
        outcome = hit_enrichment.EnrichResult()
        if sources.enabled["semantic_scholar"]:
            # No RetryOn429: hit_enrichment waits on Retry-After itself.
            async with semantic_scholar.new_client(
                email=sources.contact_email,
                api_key=sources.api_keys.get("semantic_scholar"),
                transport=transport,
                retry_429=False,
            ) as http:
                outcome = await hit_enrichment.enrich(session, http, ws, run)
        if sources.enabled["arxiv"]:
            # Asked even when S2 is busy: another host, and without a key S2 is always busy.
            refs = await hit_enrichment.refs_for_arxiv(session, ws, run)
            result = await _arxiv_fallback(session, refs, ctx.get("arxiv_transport"))
            outcome = replace(outcome, arxiv_filled=result.filled, arxiv_rate_limited=result.rate_limited)
        cleared += await hit_enrichment.clear_stale_no_abstract(session, ws)
        outcome = replace(outcome, suggestions_cleared=cleared)
    logger.info("enrich_hits for %s: %s", workspace_id, outcome)
