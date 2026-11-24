"""Embedding a paper's references and the notes that cite them, so the references list can rank by closeness."""

import uuid

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.citations.references import _TAKE_LOCK, REFERENCES_LOCK
from app.models import ExternalRef, Note, NoteEmbedding, paper_references
from app.providers import embedding

EMBED_BATCH = 64  # titles embedded, and committed, per lock hold


async def embed_new(session: AsyncSession, embedder) -> None:
    """Vectors for reference titles and notes that have none, or were made by another source or before an edit, under
    the embedder's name. With no search model (embedder None) there are none to make: the listing ranks by its other
    signals (D136). Every source embeds them, cloud or not (P3 = A, D161): no source-specific branch."""
    if embedder is None:
        return
    model_name = embedder.name
    # Only references a listing can rank need a vector: cited by or citing a library paper, or on To read. Bulk
    # harvests store 100k+ others; embedding them under the lock stalled every fetch. Batches commit, so the lock
    # is held for one batch at a time.
    needed = or_(
        ExternalRef.queued_at.is_not(None),
        select(paper_references.c.ref_id).where(paper_references.c.ref_id == ExternalRef.id).exists(),
    )
    while True:
        await session.execute(_TAKE_LOCK, {"key": REFERENCES_LOCK})
        refs = (
            await session.execute(
                select(ExternalRef.id, ExternalRef.title)
                .where(or_(ExternalRef.title_embedding.is_(None), ExternalRef.title_embed_model != model_name), needed)
                .limit(EMBED_BATCH)
            )
        ).all()
        if not refs:
            break
        vectors = await embedding.embed_documents(embedder, [title for _, title in refs])
        for (ref_id, _), vector in zip(refs, vectors):
            await session.execute(
                update(ExternalRef)
                .where(ExternalRef.id == ref_id)
                .values(title_embedding=vector, title_embed_model=model_name)
            )
        await session.commit()
    # ponytail: notes are embedded on save (workers/references.embed_note). This re-checks every note at each fetch,
    # the catch-up for the ones that missed it (a failed enqueue, or no search model then). With thousands of notes
    # that scan gets slow: index by noted_at, or drop it.
    await embed_notes(session, embedder)


async def embed_notes(session: AsyncSession, embedder, note_ids: list[uuid.UUID] | None = None) -> int:
    """Vectors for notes that have none, or were edited since or made by another model, under the embedder's name:
    all of them, or only `note_ids`. Returns how many were embedded. With no search model (embedder None) there are
    none to make, so 0."""
    if embedder is None:
        return 0
    model_name = embedder.name
    await session.execute(_TAKE_LOCK, {"key": REFERENCES_LOCK})
    query = (
        select(Note.id, Note.body, Note.updated_at)
        .outerjoin(NoteEmbedding, NoteEmbedding.note_id == Note.id)
        .where(
            or_(
                NoteEmbedding.note_id.is_(None),
                NoteEmbedding.noted_at < Note.updated_at,
                NoteEmbedding.embed_model != model_name,
            )
        )
    )
    if note_ids is not None:
        query = query.where(Note.id.in_(note_ids))
    notes = (await session.execute(query)).all()
    if notes:
        vectors = await embedding.embed_documents(embedder, [body for _, body, _ in notes])
        for (note_id, _, updated_at), vector in zip(notes, vectors):
            await session.merge(
                NoteEmbedding(note_id=note_id, embedding=vector, embed_model=model_name, noted_at=updated_at)
            )
    await session.commit()
    return len(notes)
