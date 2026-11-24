"""Listing references: one paper's, ranked and summarized, and the library-wide view with co-citations and coverage."""

import dataclasses
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.citations.references import (
    CO_CITATION_SUMMARY,
    COCITED_MIN,
    FETCH_FAILED,
    FETCH_STALE,
    Listing,
    ReferenceRow,
    Summary,
)
from app.core.papers import papers
from app.core.workspaces import workspaces

# The one in-library match (D121, D165): the tab, the References page and the graph all compose this. A reference is a
# library paper when it was imported as one, or a paper has its OpenAlex ID, its DOI in any case, or its arXiv DOI.
# openalex_id/arxiv_id come from external_ids (Phase 0b), not the legacy columns of the same name — those stay
# mapped on the model but are no longer written by anything, so a reference discovered after this migration would
# never match here if this still joined on them directly.
IN_LIBRARY = """in_library(ref_id, paper_id) AS (
  SELECT id, imported_as FROM external_refs WHERE imported_as IS NOT NULL
  UNION SELECT r.id, p.id FROM external_refs r JOIN papers p ON p.openalex_id = r.external_ids->>'openalex'
         WHERE r.imported_as IS NULL
  UNION SELECT r.id, p.id FROM external_refs r JOIN papers p ON lower(p.doi) = lower(r.doi)
         WHERE r.imported_as IS NULL
  UNION SELECT r.id, p.id FROM external_refs r
           JOIN papers p ON lower(p.doi) = '10.48550/arxiv.' || lower(r.external_ids->>'arxiv')
         WHERE r.imported_as IS NULL
)"""

# ponytail: no vector index; at library scale (hundreds of refs, tens of notes) a scan beats an HNSW build. Add one
# when a library passes ~50k references.
NOTE_SIMILARITY = """(SELECT max(1 - (r.title_embedding <=> n.embedding)) FROM note_embeddings n
             WHERE n.embed_model = r.title_embed_model)"""

# D80's tiers, written once. Bare output-column names, so Postgres reads them as the SELECT's own columns in both
# statements (pr.position in the tab, l.position on the page).
RANK = "cocitation DESC, note_similarity DESC NULLS LAST, has_pdf DESC, cited_by_count DESC NULLS LAST, position"

_LISTING = text(
    f"""
    WITH {IN_LIBRARY}
    SELECT r.id, r.title, r.authors, r.year, r.venue, r.doi,
           r.external_ids->>'arxiv' AS arxiv_id, r.external_ids->>'openalex' AS openalex_id,
           r.external_ids->>'semantic_scholar' AS s2_id, r.cited_by_count,
           jsonb_array_length(r.pdf_urls) > 0 AS has_pdf,
           (SELECT count(DISTINCT other.paper_id) FROM paper_references other
             WHERE other.ref_id = r.id AND other.direction = pr.direction) AS cocitation,
           {NOTE_SIMILARITY} AS note_similarity,
           (SELECT il.paper_id FROM in_library il WHERE il.ref_id = r.id ORDER BY il.paper_id LIMIT 1) AS paper_id,
           (SELECT p.file_path IS NOT NULL FROM in_library il JOIN papers p ON p.id = il.paper_id
             WHERE il.ref_id = r.id ORDER BY il.paper_id LIMIT 1) AS paper_has_pdf,
           pr.position, r.queued_at
      FROM paper_references pr
      JOIN external_refs r ON r.id = pr.ref_id
     WHERE pr.paper_id = :paper_id AND pr.direction = :direction
     ORDER BY {RANK}
    """
)


def shown_state(state: str, error: str | None, requested_at: datetime | None) -> tuple[str, str | None]:
    """The 10-minute stale rule (a lost job, e.g. a worker restart mid-fetch): shown as failed, so Try again claims
    it as request_fetch does. Shared by the tab's listing and the References page's coverage."""
    if state == "fetching" and (requested_at is None or requested_at < datetime.now(timezone.utc) - FETCH_STALE):
        return "failed", FETCH_FAILED
    return state, error


async def listing(session: AsyncSession, paper_id: uuid.UUID, direction: str) -> Listing:
    paper = await papers.get_paper(session, paper_id)
    rows = [
        ReferenceRow(**{key: value for key, value in row._mapping.items() if key != "note_similarity"})
        for row in await session.execute(_LISTING, {"paper_id": paper_id, "direction": direction})
    ]
    state, error = shown_state(paper.references_state, paper.references_error, paper.references_requested_at)
    return Listing(
        state=state,
        error=error,
        direction=direction,
        summary=summarize(rows),
        rows=rows,
    )


def summarize(rows: Sequence[ReferenceRow]) -> Summary:
    return Summary(
        cited_by_3plus=sum(row.cocitation >= CO_CITATION_SUMMARY for row in rows),
        with_pdf=sum(row.has_pdf for row in rows),
    )


@dataclass(frozen=True)
class UnfetchedPaper:
    id: uuid.UUID
    title: str
    state: str  # none | fetching | failed (shown state)
    error: str | None


@dataclass(frozen=True)
class Coverage:
    fetched: int
    total: int
    unfetched: list[UnfetchedPaper]  # by title, then id


@dataclass(frozen=True)
class ReferencePage:
    coverage: Coverage
    to_read: list[ReferenceRow]  # newest queued_at first
    cited_by_several: list[ReferenceRow]  # D80 order
    citing_several: list[ReferenceRow]  # newest first (D177); cocitation = scope papers it cites


_PAGE = text(
    f"""
    WITH {IN_LIBRARY}, scope(paper_id) AS (
      SELECT p.id FROM papers p
       WHERE CAST(:workspace AS uuid) IS NULL
          OR EXISTS (SELECT 1 FROM workspace_papers wp WHERE wp.paper_id = p.id AND wp.workspace_id = :workspace)
    ), linked(ref_id, cocitation, citing, position) AS (
      SELECT pr.ref_id,
             count(DISTINCT pr.paper_id) FILTER (WHERE pr.direction = 'cites'),
             count(DISTINCT pr.paper_id) FILTER (WHERE pr.direction = 'cited_by'),
             min(pr.position)
        FROM paper_references pr JOIN scope s ON s.paper_id = pr.paper_id
       GROUP BY pr.ref_id
    )
    SELECT r.id, r.title, r.authors, r.year, r.venue, r.doi,
           r.external_ids->>'arxiv' AS arxiv_id, r.external_ids->>'openalex' AS openalex_id,
           r.external_ids->>'semantic_scholar' AS s2_id, r.cited_by_count,
           jsonb_array_length(r.pdf_urls) > 0 AS has_pdf, coalesce(l.cocitation, 0) AS cocitation,
           coalesce(l.citing, 0) AS citing, {NOTE_SIMILARITY} AS note_similarity,
           NULL::uuid AS paper_id, NULL::boolean AS paper_has_pdf, coalesce(l.position, 0) AS position, r.queued_at
      FROM external_refs r LEFT JOIN linked l ON l.ref_id = r.id
     WHERE NOT EXISTS (SELECT 1 FROM in_library il WHERE il.ref_id = r.id)
       AND (l.ref_id IS NOT NULL OR (r.queued_at IS NOT NULL AND CAST(:workspace AS uuid) IS NULL))
       AND (r.queued_at IS NOT NULL OR l.cocitation >= :cocited_min OR l.citing >= :cocited_min)
     ORDER BY {RANK}, r.id
    """
)


async def library_listing(session: AsyncSession, workspace_id: uuid.UUID | None = None) -> ReferencePage:
    """The References page (D121, D166): To read, works several scope papers cite, and recent works that cite
    several of them (D177), across the library or one workspace. Raises NotFound for an unknown workspace."""
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    raw = list(await session.execute(_PAGE, {"workspace": workspace_id, "cocited_min": COCITED_MIN}))
    rows = [
        ReferenceRow(**{key: value for key, value in row._mapping.items() if key not in ("note_similarity", "citing")})
        for row in raw
    ]
    citing_by_id = {row.id: row.citing for row in raw}
    to_read = sorted((r for r in rows if r.queued_at is not None), key=lambda r: (-r.queued_at.timestamp(), r.id))
    cited_by_several = [r for r in rows if r.cocitation >= COCITED_MIN]
    citing_several = sorted(
        (dataclasses.replace(r, cocitation=citing_by_id[r.id]) for r in rows if citing_by_id[r.id] >= COCITED_MIN),
        key=lambda r: (-(r.year or -1), -r.cocitation, r.id),
    )
    coverage_rows = list(
        await session.execute(
            text(
                """
                SELECT p.id, p.title, p.references_state, p.references_error, p.references_requested_at,
                       p.references_state = 'ready' OR EXISTS (
                           SELECT 1 FROM paper_references pr WHERE pr.paper_id = p.id
                       ) AS fetched
                  FROM papers p
                 WHERE CAST(:workspace AS uuid) IS NULL
                    OR EXISTS (
                        SELECT 1 FROM workspace_papers wp WHERE wp.paper_id = p.id AND wp.workspace_id = :workspace
                    )
                """
            ),
            {"workspace": workspace_id},
        )
    )
    unfetched = sorted(
        (row for row in coverage_rows if not row.fetched),
        key=lambda row: (row.title, row.id),
    )
    coverage = Coverage(
        fetched=sum(1 for row in coverage_rows if row.fetched),
        total=len(coverage_rows),
        unfetched=[
            UnfetchedPaper(
                row.id, row.title, *shown_state(row.references_state, row.references_error, row.references_requested_at)
            )
            for row in unfetched
        ],
    )
    return ReferencePage(
        coverage=coverage, to_read=to_read, cited_by_several=cited_by_several, citing_several=citing_several
    )
