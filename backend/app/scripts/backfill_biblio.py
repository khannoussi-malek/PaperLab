"""Fills volume, issue, pages, editors, pmid and pmcid for papers that lack some of them: Crossref by DOI, OpenAlex
for the PubMed ids.

Run once in the api container: `python -m app.scripts.backfill_biblio`. Paced (Crossref's polite pool allows about 3
requests a second), idempotent (only NULL fields are filled), and never touches a field the owner set by hand.
A paper with no PubMed record (most outside biomedicine) keeps a NULL pmid, so every rerun asks about it again:
run it once after an upgrade, not on a schedule.
"""

import asyncio
import uuid

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import enrichment, paper_sources
from app.db import SessionLocal
from app.models import Paper
from app.providers import crossref, openalex

DELAY = 0.4


async def run(
    session: AsyncSession,
    crossref_http: httpx.AsyncClient | None,
    openalex_http: httpx.AsyncClient | None,
    *,
    delay: float = DELAY,
    only: list[uuid.UUID] | None = None,
) -> dict[str, int]:
    columns = [getattr(Paper, name) for name in enrichment.BIBLIO_FIELDS]
    # Editors alone never select a paper: most papers have none.
    wanted = [getattr(Paper, name) for name in ("volume", "issue", "pages", "pmid", "pmcid")]
    query = select(Paper.id, *columns).where(Paper.doi.is_not(None), or_(*(c.is_(None) for c in wanted)))
    if only is not None:
        query = query.where(Paper.id.in_(only))
    rows = (await session.execute(query.order_by(Paper.created_at))).all()
    summary = {"checked": len(rows), "updated": 0}
    for paper_id, *before in rows:
        asked = await enrichment.fill_biblio(session, paper_id, crossref_http, openalex_http)
        after = (await session.execute(select(*columns).where(Paper.id == paper_id))).one()
        summary["updated"] += list(after) != before
        if asked:
            await asyncio.sleep(delay)  # pacing only after a request
    return summary


async def main() -> None:
    async with SessionLocal() as session:
        sources = await paper_sources.get(session)
        email = sources.contact_email
        cr = crossref.new_client(email=email) if sources.enabled["crossref"] else None
        key = sources.api_keys["openalex"]
        oa = openalex.new_client(email=email, api_key=key) if sources.enabled["openalex"] else None
        try:
            summary = await run(session, cr, oa)
        finally:
            for client in (cr, oa):
                if client:
                    await client.aclose()
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
