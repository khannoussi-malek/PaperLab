"""Vector top-k over chunks, scoped to papers or a workspace, with a per-paper diversity cap."""

import asyncio
import uuid
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import embedding_index, embedding_sources
from app.core.errors import Conflict
from app.models import workspace_papers
from app.providers import embedding
from app.providers.base import LLMError, LLMUnavailable, TextEmbedder

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

# D136: what the MCP server passes on with Conflict("search_not_set_up"); the app words it itself (spec §5, §6).
SEARCH_NOT_SET_UP = "Search isn't set up. Download the search model in Settings to search long papers and workspaces."
# P1: what the MCP tool passes on with Conflict("search_rebuilding"); the app words it from GET /api/embedding.
SEARCH_REBUILDING = "Search is being rebuilt with {label}: {done} of {total} {papers}. Try again when it finishes."
# D155: a revoked key or a server that went away, at question time. The chat panel shows it as sent.
QUESTION_FAILED = "Search couldn't embed your question: {reason}."


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    paper_id: uuid.UUID
    page: int
    section: str | None
    bbox: list[Rect]
    text: str
    distance: float | None = None  # None when chat sends the whole paper instead of retrieving


async def _built(source: embedding_sources.Source) -> TextEmbedder:
    model = await asyncio.to_thread(embedding.build, source)
    if model is None:  # Built-in, and the model isn't downloaded yet (D136)
        raise Conflict("search_not_set_up", detail=SEARCH_NOT_SET_UP)
    return model


async def query_embedder(session: AsyncSession, embedder: TextEmbedder | None = None) -> TextEmbedder:
    """What embeds a question: `embedder` when the caller passes one (tests, evals), else the active search source's,
    built for this question (D151). Raises Conflict("search_not_set_up") while Built-in has no model (D136)."""
    if embedder is not None:
        return embedder
    return await _built(await embedding_sources.active(session))


async def searchable(
    session: AsyncSession, paper_ids: list[uuid.UUID], embedder: TextEmbedder | None = None
) -> TextEmbedder:
    """D156's gate before a search in `paper_ids`, in order:
    - no source → search_not_set_up;
    - a paper in scope still waiting for the rebuild → search_rebuilding, with how far it got;
    - vectors from another model in scope → embedding_model_changed;
    - else the embedder.
    The scope decides: mid-rebuild, a paper already re-embedded answers, and a library search with any paper still
    waiting pauses (P1 never gives partial results)."""
    source = await embedding_sources.active(session)
    model = embedder if embedder is not None else await _built(source)
    rebuild = await embedding_index.rebuild(session, source)
    if rebuild is not None and await embedding_index.pending_in(session, source, paper_ids):
        papers = "paper" if rebuild.total == 1 else "papers"
        detail = SEARCH_REBUILDING.format(label=source.label, done=rebuild.done, total=rebuild.total, papers=papers)
        raise Conflict("search_rebuilding", detail=detail, done=rebuild.done, total=rebuild.total)
    await embedding_index.check_model(session, model.name, paper_ids)
    return model


def _to_chunk(row, distance: float | None = None) -> RetrievedChunk:
    """Row → RetrievedChunk. Shared with chat.py's chunk_sources: both a raw-SQL row and an ORM row
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
    """The k chunks nearest to the query, closest first. embedder=None embeds the question with the active search
    source (query_embedder); a source that fails raises Conflict with QUESTION_FAILED's sentence (D155).

    Scope: paper_ids, workspace_id, or neither (the whole library). A scope that resolves to 2+ papers (a
    workspace with several members, or 2+ paper_ids) keeps at most per_paper (default MAX_PER_PAPER) chunks
    from each paper; a workspace with exactly one paper is uncapped, same as passing that one paper's id.
    """
    if paper_ids is not None and workspace_id is not None:
        raise ValueError("retrieve takes paper_ids or workspace_id, not both")
    if workspace_id is not None:
        # Ids first, not a subquery in the scan: with literal ids the planner sees a small scope and sorts it
        # exactly; behind ARRAY(subquery) it guesses, picks HNSW, and bloat can starve the scan (see above).
        members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
        paper_ids = list(await session.scalars(members))
    if paper_ids is not None and not paper_ids:
        return []
    # The cap is decided from the resolved paper_ids, not from workspace_id itself: a workspace can resolve to
    # just one paper, which must be as uncapped as passing that paper's id directly.
    if per_paper is None and paper_ids is not None and len(paper_ids) > 1:
        per_paper = MAX_PER_PAPER
    model = await query_embedder(session, embedder)
    try:
        question = await embedding.embed_query(model, query)
    except (LLMUnavailable, LLMError) as exc:
        raise Conflict(QUESTION_FAILED.format(reason=str(exc).rstrip("."))) from exc
    params = {"q": question, "k": k, "candidates": max(CANDIDATES, k)}
    params["per_paper"] = k if per_paper is None else per_paper
    if paper_ids is None:
        statement = NEAREST
    else:
        statement, params["paper_ids"] = NEAREST_IN_PAPERS, list(paper_ids)
    await session.execute(ITERATIVE_SCAN)  # SET LOCAL: ends with the caller's transaction
    rows = await session.execute(statement, params)
    return [_to_chunk(row, distance=row.distance) for row in rows]
