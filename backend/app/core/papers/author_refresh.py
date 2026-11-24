"""Refreshing a paper's authors from OpenAlex: their names, ORCIDs and institutions, at most once per period."""

import uuid
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers.openalex_fields import short_id
from app.models import Author, paper_authors
from app.providers import openalex

AUTHOR_REFRESH_AFTER = timedelta(days=30)


async def _replace_authorships(session: AsyncSession, paper_id: uuid.UUID, work: dict[str, Any]) -> list[str]:
    """Upserts the work's authors by OpenAlex ID and links them in author order. Returns their OpenAlex IDs."""
    first_listing: dict[str, tuple[int, dict]] = {}
    for position, authorship in enumerate(work.get("authorships") or [], start=1):
        if openalex_id := short_id(authorship["author"].get("id")):  # never create an author from a name alone
            first_listing.setdefault(openalex_id, (position, authorship))
    await session.execute(delete(paper_authors).where(paper_authors.c.paper_id == paper_id))
    if not first_listing:
        return []

    new_authors = [
        {"openalex_id": oid, "display_name": a["author"]["display_name"], "orcid": short_id(a["author"].get("orcid"))}
        for oid, (_, a) in first_listing.items()
    ]
    # ponytail: two OpenAlex IDs sharing one ORCID break authors.orcid UNIQUE, and the paper keeps no authors (still
    # non-fatal). Drop the ORCID on conflict if OpenAlex's duplicate profiles ever show up.
    await session.execute(pg_insert(Author).values(new_authors).on_conflict_do_nothing(index_elements=["openalex_id"]))
    rows = await session.execute(select(Author.openalex_id, Author.id).where(Author.openalex_id.in_(first_listing)))
    author_ids = dict(rows.all())
    links = [
        {
            "paper_id": paper_id,
            "author_id": author_ids[oid],
            "position": position,
            "is_corresponding": bool(a.get("is_corresponding")),
            # The affiliation printed on this paper, not the author's current one.
            "institution": next((i["display_name"] for i in a.get("institutions") or []), None),
        }
        for oid, (position, a) in first_listing.items()
    ]
    await session.execute(insert(paper_authors), links)
    return list(first_listing)


async def refresh_authors(session: AsyncSession, http: httpx.AsyncClient, openalex_ids: list[str]) -> None:
    """Fetches details (h-index, works count, ...) for authors not fetched in the last 30 days, 50 per request."""
    stale = list(
        await session.scalars(
            select(Author.openalex_id).where(
                Author.openalex_id.in_(openalex_ids),
                or_(Author.fetched_at.is_(None), Author.fetched_at < func.now() - AUTHOR_REFRESH_AFTER),
            )
        )
    )
    if not stale:
        return
    stale.sort(key=openalex_ids.index)  # author order, so requests are predictable
    for record in await openalex.get_authors(http, stale):
        values = {
            "display_name": record["display_name"],
            "orcid": short_id(record.get("orcid")),
            "alt_names": record.get("display_name_alternatives") or [],
            "last_institution": next((i["display_name"] for i in record.get("last_known_institutions") or []), None),
            "works_count": record.get("works_count"),
            "cited_by_count": record.get("cited_by_count"),
            "h_index": (record.get("summary_stats") or {}).get("h_index"),
            "topics": [{"label": t["display_name"], "count": t.get("count")} for t in record.get("topics") or []],
            "fetched_at": func.now(),
        }
        await session.execute(update(Author).where(Author.openalex_id == short_id(record["id"])).values(**values))
    await session.commit()
