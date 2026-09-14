"""Vector top-k over chunks. M5 adds category_id and the diversity cap as keyword arguments, M8 hybrid search."""

import asyncio
import uuid
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers import embedding

Rect = tuple[float, float, float, float]

# <=> (cosine distance) is the only operator the HNSW index (vector_cosine_ops) can serve.
_NEAREST = """
SELECT id, paper_id, page, section_title, bbox, text, embedding <=> :q AS distance
FROM chunks
WHERE embedding IS NOT NULL {scope}
ORDER BY embedding <=> :q
LIMIT :k
"""
NEAREST = text(_NEAREST.format(scope="")).bindparams(bindparam("q", type_=Vector(768)))
# ponytail: HNSW with a filter post-filters within ef_search and can silently drop rows (spike: 0 of 8).
# Before M5 ships multi-paper scopes, run SET LOCAL hnsw.iterative_scan = relaxed_order (and re-sort).
# M4 is unaffected: single-paper queries use the (paper_id, page) index and an exact sort.
NEAREST_IN_PAPERS = text(_NEAREST.format(scope="AND paper_id = ANY(:paper_ids)")).bindparams(
    bindparam("q", type_=Vector(768))
)


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
    k: int = 8,
    embedder=None,
) -> list[RetrievedChunk]:
    """The k chunks nearest to the query, closest first. embedder=None uses the process-cached model."""
    model = embedder if embedder is not None else await asyncio.to_thread(embedding.get_model)
    params = {"q": await embedding.embed_query(model, query), "k": k}
    if paper_ids is None:
        statement = NEAREST
    else:
        statement, params["paper_ids"] = NEAREST_IN_PAPERS, list(paper_ids)
    rows = await session.execute(statement, params)
    return [_to_chunk(row, distance=row.distance) for row in rows]
