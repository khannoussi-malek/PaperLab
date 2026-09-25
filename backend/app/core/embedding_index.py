"""The embedding index: which model the stored vectors came from, and never mixing two models' vectors.

There is one embedding model and vector(768) is fixed at the column. `settings.embed_model` names it: the model
vectors are recorded and checked under, and it follows the shipped search model (`search_model.SHIPPED`), which is
what `load()` actually runs. Setting it by hand would mislabel vectors, not switch models. If it changed anyway while
chunks exist, a new query vector would be compared with vectors from the old model and retrieval would quietly
return nonsense. So chat refuses those papers until the library is re-indexed with the new model.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.models import Chunk


@dataclass(frozen=True)
class IndexedModel:
    model: str
    chunks: int


@dataclass(frozen=True)
class EmbeddingStatus:
    model: str  # settings.embed_model: what new chunks and questions are embedded with
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


def _lacking(name: str):
    """A chunk without a vector from `name`: none yet, or another source's."""
    return or_(Chunk.embedding.is_(None), Chunk.embed_model != name)


async def papers_to_embed(
    session: AsyncSession, name: str, paper_ids: list[uuid.UUID] | None = None
) -> list[uuid.UUID]:
    """Papers with a chunk that has no vector from `name` (D155): what a switch and Try again queue, and what a
    missing_only job checks before it pays a source again. `paper_ids` narrows it to those papers."""
    query = select(Chunk.paper_id).group_by(Chunk.paper_id).having(func.bool_or(_lacking(name)))
    if paper_ids is not None:
        query = query.where(Chunk.paper_id.in_(paper_ids))
    return list(await session.scalars(query))
