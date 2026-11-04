"""Top-k over chunks, by vector or fused with a keyword ranking (the Settings → Search switch), scoped to papers or a
workspace, with a per-paper diversity cap."""

import asyncio
import uuid
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import embedding_index, embedding_sources
from app.core.errors import Conflict
from app.core.papers import ABSTRACT_PAGE
from app.models import EmbeddingSource, Paper, PaperStatus, workspace_papers
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


# Hybrid search: the vector candidates and up to as many keyword candidates, fused by reciprocal rank (each list adds
# 1 / (RRF_K + rank)), then the same per-paper cap. The keyword score sums each question word's IDF over the scope,
# not ts_rank: ts_rank has no IDF, so "patient" counts as much as "itraconazole", and websearch_to_tsquery ANDs every
# word, which a whole question never matches. Matches go through the GIN index on tsv first, then only they are scored.
# ponytail: 'english' stemming won't join "haemodialysis" to "dialysis"; the vector half has to carry those.
# The vector ranks count from the far end: relaxed_order (below) can return `nearest` slightly out of order, and a
# window ORDER BY distance would take that order as already sorted. Postgres can't take it as sorted DESC.
RRF_K = 60
# Longer than this is a passage, not a question (the paper deck sends a whole section): vectors alone. A keyword ranking
# of its hundreds of words would be slow, with each word counted over the scope, and would mean nothing.
MAX_HYBRID_CHARS = 1_000
MAX_TERMS = 32  # the rarest words of a question, which are the ones that tell chunks apart
_HYBRID = """
WITH vector AS (
  SELECT id, count(*) OVER () + 1 - row_number() OVER (ORDER BY distance DESC) AS rank
  FROM (
    SELECT id, embedding <=> :q AS distance
    FROM chunks
    WHERE embedding IS NOT NULL {scope}
    ORDER BY embedding <=> :q
    LIMIT :candidates
  ) AS nearest
),
terms AS MATERIALIZED (
  SELECT DISTINCT quote_literal(lexeme)::tsquery AS term
  FROM unnest(tsvector_to_array(to_tsvector('english', :question))) AS lexeme
),
total AS (SELECT count(*)::float AS n FROM chunks WHERE {words} {scope}),
weights AS MATERIALIZED (
  SELECT term, ln((SELECT n FROM total) / df) AS weight
  FROM (
    SELECT term, (SELECT count(*) FROM chunks WHERE {words} {scope} AND tsv @@ term) AS df
    FROM terms
    OFFSET 0  -- keeps the planner from counting each term once per use of df below
  ) AS counted
  WHERE df > 0 AND df < (SELECT n FROM total)  -- a word in every chunk tells them apart by nothing
  ORDER BY df
  LIMIT :max_terms
),
lexical AS (
  SELECT id, rank() OVER (ORDER BY score DESC) AS rank  -- ties share a rank, so they leave the vector order alone
  FROM (
    SELECT id, (SELECT sum(weight) FROM weights WHERE tsv @@ weights.term) AS score
    FROM chunks
    WHERE {words} {scope} AND tsv @@ (SELECT string_agg(term::text, ' | ')::tsquery FROM weights)
    ORDER BY score DESC, embedding <=> :q, id  -- more ties than candidates: keep the nearest
    LIMIT :candidates
  ) AS matched
),
fused AS (
  SELECT id, sum(1.0 / (:rrf_k + rank)) AS score
  FROM (SELECT id, rank FROM vector UNION ALL SELECT id, rank FROM lexical) AS both_lists
  GROUP BY id
),
ranked AS (
  SELECT c.id, c.paper_id, c.page, c.section_title, c.bbox, c.text, coalesce(c.embedding <=> :q, 2) AS distance,
    f.score,
    row_number() OVER (PARTITION BY c.paper_id ORDER BY f.score DESC, c.embedding <=> :q) AS nth
  FROM fused AS f JOIN chunks AS c ON c.id = f.id
)
SELECT id, paper_id, page, section_title, bbox, text, distance
FROM ranked
WHERE nth <= :per_paper
ORDER BY score DESC, distance
LIMIT :k
"""


async def hybrid_on(session: AsyncSession) -> bool:
    """The Settings → Search switch. HYBRID_SEARCH forces it on, for the evals that compare both modes."""
    return settings.hybrid_search or bool(await session.scalar(select(EmbeddingSource.hybrid_search)))


def _nearest(
    in_papers: bool, in_chunks: bool, hybrid: bool = False, skip_busy: bool = False, unembedded_words: bool = False
):
    """The candidate query with its scope: papers, given chunks (M16, D49), both or neither, minus papers embedding.
    `unembedded_words`: the keyword half of hybrid also reads chunks with no vector yet."""
    scope = " ".join(
        clause
        for clause, wanted in (
            ("AND paper_id = ANY(:paper_ids)", in_papers),
            ("AND id = ANY(:chunk_ids)", in_chunks),
            ("AND paper_id <> ALL(:busy)", skip_busy),
        )
        if wanted
    )
    query = _HYBRID if hybrid else _NEAREST
    words = "TRUE" if unembedded_words else "embedding IS NOT NULL"
    return text(query.replace("{words}", words).format(scope=scope)).bindparams(bindparam("q", type_=Vector(768)))


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

    @property
    def from_abstract(self) -> bool:
        """The abstract chunk of a paper saved without a PDF: no page to show or jump to."""
        return self.page == ABSTRACT_PAGE


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
    chunk_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """The k chunks nearest to the query, closest first (with hybrid search on and a scope wider than one paper, best
    fused rank first). embedder=None embeds the question with the active search source (query_embedder); a source
    that fails raises Conflict with QUESTION_FAILED's sentence (D155).

    Scope: paper_ids, workspace_id, or neither (the whole library). A scope that resolves to 2+ papers (a
    workspace with several members, or 2+ paper_ids) keeps at most per_paper (default MAX_PER_PAPER) chunks
    from each paper; a workspace with exactly one paper is uncapped, same as passing that one paper's id.
    chunk_ids narrows the scope to those chunks (M16); an empty list returns [] without embedding the query.
    """
    if paper_ids is not None and workspace_id is not None:
        raise ValueError("retrieve takes paper_ids or workspace_id, not both")
    if workspace_id is not None:
        # Ids first, not a subquery in the scan: with literal ids the planner sees a small scope and sorts it
        # exactly; behind ARRAY(subquery) it guesses, picks HNSW, and bloat can starve the scan (see above).
        members = select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == workspace_id)
        paper_ids = list(await session.scalars(members))
    if (paper_ids is not None and not paper_ids) or (chunk_ids is not None and not chunk_ids):
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
    # Hybrid only across papers: inside one paper its own topic words are in most chunks, and the single-paper eval
    # lost recall (@4 0.95 -> 0.90, @8 1.00 -> 0.95); the workspace eval gained (@8 13/17 -> 16/17), 2026-11-01.
    # ponytail: a whole-library search in a one-paper library still runs hybrid; a count on every search isn't worth it.
    across_papers = paper_ids is None or len(paper_ids) > 1
    hybrid = across_papers and len(query) <= MAX_HYBRID_CHARS and await hybrid_on(session)
    # A long paper embeds across many jobs, so half of it can sit here for hours. Its vectors so far must not answer for
    # the whole in a wider search. Asked by itself, its words can: they're all there minutes after upload, and on the
    # fixed-answer eval keywords alone matched vectors (27 and 26 of 33, measured 2026-11-04).
    # ponytail: a wider search waits for the vectors; let it use words too if people ask across a paper mid-embedding.
    busy = list(await session.scalars(select(Paper.id).where(Paper.status == PaperStatus.EMBEDDING)))
    alone = paper_ids is not None and len(paper_ids) == 1 and paper_ids[0] in busy
    hybrid = hybrid or alone
    statement = _nearest(paper_ids is not None, chunk_ids is not None, hybrid, bool(busy) and not alone, alone)
    if busy and not alone:
        params["busy"] = busy
    if hybrid:
        # Postgres refuses a NUL in text, and the vector path never sends the words to it.
        params |= {"question": query.replace("\x00", ""), "rrf_k": RRF_K, "max_terms": MAX_TERMS}
    if paper_ids is not None:
        params["paper_ids"] = list(paper_ids)
    if chunk_ids is not None:
        params["chunk_ids"] = list(chunk_ids)
    await session.execute(ITERATIVE_SCAN)  # SET LOCAL: ends with the caller's transaction
    # SET can't take a bind parameter; the setting is a validated int (1–1000).
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.hnsw_ef_search)}"))
    rows = await session.execute(statement, params)
    return [_to_chunk(row, distance=row.distance) for row in rows]
