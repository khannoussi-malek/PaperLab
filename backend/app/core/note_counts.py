"""Per-paper note counts for many papers at once: a human note anchored on that paper is a highlight, a human note
linked to it without an anchor there is a note, an AI-written note (llm / llm_edited) is an AI note."""

import uuid

from sqlalchemy import and_, case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import note_anchors, note_papers
from app.models.note import Note, Provenance

AI = (Provenance.LLM, Provenance.LLM_EDITED)
MAX_PAPERS = 2000


async def note_counts(session: AsyncSession, paper_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """{paper id: {notes, highlights, ai_notes}} for every id asked (zeros when it has none)."""
    counts = {pid: {"notes": 0, "highlights": 0, "ai_notes": 0} for pid in paper_ids}
    if not counts:
        return counts
    anchored = exists().where(
        and_(note_anchors.c.note_id == Note.id, note_anchors.c.paper_id == note_papers.c.paper_id)
    )
    kind = case((Note.provenance.in_(AI), "ai_notes"), (anchored, "highlights"), else_="notes")
    query = (
        select(note_papers.c.paper_id, kind.label("kind"), func.count().label("n"))
        .join(Note, Note.id == note_papers.c.note_id)
        .where(note_papers.c.paper_id.in_(counts))
        .group_by(note_papers.c.paper_id, kind)
    )
    for paper_id, k, n in await session.execute(query):
        counts[paper_id][k] = n
    return counts
