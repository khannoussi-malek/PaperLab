"""Vector top-k over chunks, scoped to papers or a workspace, with a per-paper diversity cap."""

import asyncio
import uuid
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import workspace_papers
from app.providers import embedding

Rect = tuple[float, float, float, float]

# ponytail: 40 candidates can starve the cap when one paper dominates them; raise CANDIDATES if the eval shows it.
CANDIDATES = 40
MAX_PER_PAPER = 3

# <=> (cosine distance) is the only operator the HNSW index (vector_cosine_ops) can serve. The candidate CTE takes
# the nearest chunks in scope; the outer query caps each paper and re-sorts, since relaxed_order (below) can return
# candidates slightly out of order.
_NEAREST = """
WITH candidates AS (
  SELECT id, paper_id, page, section_title, bbox, text, embedding <=> :q AS distance
  FROM chunks
  WHERE embedding IS NOT NULL {scope}
  ORDER BY embedding <=> :q
  LIMIT :candidates
)
SELECT id, paper_id, page, section_title, bbox, text, distance
FROM (SELECT *, row_number() OVER (PARTITION BY paper_id ORDER BY distance) AS nth FROM candidates) AS ranked
WHERE nth <= :per_paper
ORDER BY distance
LIMIT :k
"""
NEAREST = text(_NEAREST.format(scope="")).bindparams(bindparam("q", type_=Vector(768)))
NEAREST_IN_PAPERS = text(_NEAREST.format(scope="AND paper_id = ANY(:paper_ids)")).bindparams(
    bindparam("q", type_=Vector(768))
)
# With a filter, HNSW otherwise post-filters within ef_search (40) candidates and can silently return nothing.
# ponytail: an iterative scan still stops at hnsw.max_scan_tuples (20,000) or work_mem x hnsw.scan_mem_multiplier.
# Thousands of dead near-duplicate vectors (re-ingests before autovacuum) can starve it; VACUUM chunks if it shows.
ITERATIVE_SCAN = text("SET LOCAL hnsw.iterative_scan = relaxed_order")


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    paper_id: uuid.UUID
    page: int
    section: str | None
    bbox: list[Rect]
    text: str
    distance: float | None = None  # None when chat sends the whole paper instead of retrieving


def _to_chunk(row, distance: float | None = None) -> RetrievedChunk:
    """Row → RetrievedChunk. Shared with chat.py's _chunk_sources: both a raw-SQL row and an ORM row
    expose these same attributes; only retrieval's rows carry a distance."""
    return RetrievedChunk(
        id=row.id,
        paper_id=row.paper_id,
        page=row.page,
        section=row.section_title,
        bbox=[tuple(rect) for rect in row.bbox],
        text=row.text,
        distance=distance,
    )


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    paper_ids: list[uuid.UUID] | None = None,
    workspace_id: uuid.UUID | None = None,
    k: int = 8,
    embedder=None,
    per_paper: int | None = None,
) -> list[RetrievedChunk]:
    """The k chunks nearest to the query, closest first. embedder=None uses the process-cached model.

    Scope: paper_ids, workspace_id, or neither (the whole library). A scope that can cover several papers (a
    workspace, or 2+ paper_ids) keeps at most per_paper (default MAX_PER_PAPER) chunks from each paper.
    """
    if paper_ids is not None and workspace_id is not None:
        raise ValueError("retrieve takes paper_ids or workspace_id, not both")
    if per_paper is None and (workspace_id is not None or (paper_ids is not None and len(paper_ids) > 1)):
        per_paper = MAX_PER_PAPER
    if workspace_id is not None:
        # Ids first, not a subquery in the scan: with literal ids the planner sees a small scope and sorts it
        # exactly; behind ARRAY(subquery) it guesses, picks HNSW, and bloat can starve the scan (see above).
        members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
        paper_ids = list(await session.scalars(members))
    if paper_ids is not None and not paper_ids:
        return []
    model = embedder if embedder is not None else await asyncio.to_thread(embedding.get_model)
    params = {"q": await embedding.embed_query(model, query), "k": k, "candidates": max(CANDIDATES, k)}
    params["per_paper"] = per_paper or k
    if paper_ids is None:
        statement = NEAREST
    else:
        statement, params["paper_ids"] = NEAREST_IN_PAPERS, list(paper_ids)
    await session.execute(ITERATIVE_SCAN)  # SET LOCAL: ends with the caller's transaction
    rows = await session.execute(statement, params)
    return [_to_chunk(row, distance=row.distance) for row in rows]
