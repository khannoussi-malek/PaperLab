"""The embedding index: which model the stored vectors came from, and never mixing two models' vectors.

There is one embedding model and vector(768) is fixed at the column. `settings.embed_model` names it: the model
vectors are recorded and checked under, and it follows the shipped search model (`search_model.SHIPPED`), which is
what `load()` actually runs. Setting it by hand would mislabel vectors, not switch models. If it changed anyway while
chunks exist, a new query vector would be compared with vectors from the old model and retrieval would quietly
return nonsense. So chat refuses those papers until the library is re-indexed with the new model.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import DateTime, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.models import Chunk, Note, Paper


@dataclass(frozen=True)
class IndexedModel:
    model: str
    chunks: int


@dataclass(frozen=True)
class EmbeddingStatus:
    model: str  # settings.embed_model: what new chunks and questions are embedded with
    chunks: int  # chunks that have a vector
    indexed_with: list[IndexedModel]  # the models those vectors came from, most chunks first


@dataclass(frozen=True)
class Rebuild:
    done: int  # papers of the rebuild already on the new source
    total: int  # papers with chunks created at or before the rebuild started


@dataclass(frozen=True)
class LibrarySize:
    papers: int  # papers with chunks
    notes: int
    chars: int  # their chunk text and every note's text: what a switch sends, for the dialog's estimate (P3 = A)


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


def _at_or_before(started_at):
    """`Paper.created_at <= started_at`'s right side, typed explicitly: papers.created_at is timestamptz, but the
    model maps it without a time zone (Paper.created_at), so an untyped bind would compile as TIMESTAMP WITHOUT TIME
    ZONE and asyncpg would refuse the rebuild's tz-aware started_at.
    ponytail: fix at the source by mapping Paper.created_at with DateTime(timezone=True) if another caller hits this."""
    return literal(started_at, type_=DateTime(timezone=True))


async def papers_to_embed(
    session: AsyncSession, name: str, paper_ids: list[uuid.UUID] | None = None
) -> list[uuid.UUID]:
    """Papers with a chunk that has no vector from `name` (D155): what a switch and Try again queue, and what a
    missing_only job checks before it pays a source again. `paper_ids` narrows it to those papers."""
    query = select(Chunk.paper_id).group_by(Chunk.paper_id).having(func.bool_or(_lacking(name)))
    if paper_ids is not None:
        query = query.where(Chunk.paper_id.in_(paper_ids))
    return list(await session.scalars(query))


async def rebuild(session: AsyncSession, source) -> Rebuild | None:
    """How far a rebuild toward the search source has got (D156), or None when there is none to show:
    - rebuild_model isn't the source's name (a release renamed the built-in model: Settings shows its Re-index prompt,
      D137, rather than a rebuild nobody started);
    - or no paper of the rebuild is pending.
    No flag to clear: it ends when set_embeddings writes the last paper, one transaction per paper. Papers added after
    it started don't count, so a new upload never pauses search."""
    if source.rebuild_model != source.name or source.rebuild_started_at is None:
        return None
    per_paper = (
        select(Chunk.paper_id, func.bool_or(_lacking(source.name)).label("pending"))
        .join(Paper, Paper.id == Chunk.paper_id)
        .where(Paper.created_at <= _at_or_before(source.rebuild_started_at))
        .group_by(Chunk.paper_id)
        .subquery()
    )
    counts = select(func.count(), func.count().filter(per_paper.c.pending)).select_from(per_paper)
    total, pending = (await session.execute(counts)).one()
    return None if pending == 0 else Rebuild(done=total - pending, total=total)


async def pending_in(session: AsyncSession, source, paper_ids: list[uuid.UUID]) -> bool:
    """Whether any of these papers still waits for the rebuild: one it counts, with a chunk not on the new source."""
    query = (
        select(Chunk.id)
        .join(Paper, Paper.id == Chunk.paper_id)
        .where(
            Chunk.paper_id.in_(paper_ids),
            Paper.created_at <= _at_or_before(source.rebuild_started_at),
            _lacking(source.name),
        )
    )
    return await session.scalar(query.limit(1)) is not None


async def library_size(session: AsyncSession) -> LibrarySize:
    """What a switch to a cloud source sends (D157, P3 = A): every paper's chunks and every note."""
    papers, chunk_chars = (
        await session.execute(
            select(func.count(func.distinct(Chunk.paper_id)), func.coalesce(func.sum(func.length(Chunk.text)), 0))
        )
    ).one()
    note_query = select(func.count(), func.coalesce(func.sum(func.length(Note.body)), 0)).select_from(Note)
    notes, note_chars = (await session.execute(note_query)).one()
    return LibrarySize(papers=papers, notes=notes, chars=chunk_chars + note_chars)
