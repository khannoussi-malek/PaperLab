"""The embedding index: which model the stored vectors came from, and never mixing two models' vectors.

There is one embedding model (EMBED_MODEL) and vector(768) is fixed at the column. If EMBED_MODEL changes while
chunks exist, a new query vector would be compared with vectors from the old model and retrieval would quietly
return nonsense. So chat refuses those papers until the library is re-indexed with the new model.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.models import Chunk


@dataclass(frozen=True)
class IndexedModel:
    model: str
    chunks: int


@dataclass(frozen=True)
class EmbeddingStatus:
    model: str  # EMBED_MODEL: what new chunks and questions are embedded with
    chunks: int  # chunks that have a vector
    indexed_with: list[IndexedModel]  # the models those vectors came from, most chunks first


async def status(session: AsyncSession, model: str) -> EmbeddingStatus:
    count = func.count().label("chunks")
    rows = await session.execute(
        select(Chunk.embed_model, count)
        .where(Chunk.embedding.is_not(None))
        .group_by(Chunk.embed_model)
        .order_by(count.desc(), Chunk.embed_model)
    )
    indexed = [IndexedModel(name, chunks) for name, chunks in rows]
    return EmbeddingStatus(model=model, chunks=sum(i.chunks for i in indexed), indexed_with=indexed)


async def check_model(session: AsyncSession, model: str, paper_ids: list[uuid.UUID]) -> None:
    """Raises Conflict("embedding_model_changed") when any of these papers has vectors from another model."""
    other = select(Chunk.id).where(
        Chunk.paper_id.in_(paper_ids), Chunk.embedding.is_not(None), Chunk.embed_model != model
    )
    if await session.scalar(other.limit(1)) is not None:
        raise Conflict("embedding_model_changed")


async def indexed_papers(session: AsyncSession) -> list[uuid.UUID]:
    """Every paper that has chunks: what a library re-index embeds again."""
    return list(await session.scalars(select(Chunk.paper_id).distinct()))


async def unembedded_papers(session: AsyncSession) -> list[uuid.UUID]:
    """Papers with chunks and no vectors: what a finished model download queues for embedding (D137). Whatever their
    status: a paper mid-ingest when the model landed has chunks and no vectors, and would otherwise never get any."""
    query = select(Chunk.paper_id).group_by(Chunk.paper_id).having(func.count(Chunk.embedding) == 0)
    return list(await session.scalars(query))
