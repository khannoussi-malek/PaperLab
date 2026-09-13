"""Notes and their anchors. The provenance rules live here and nowhere else:

- LLM responses go to llm_outputs, never directly into notes.            (M4)
- Promoting an LLM fragment creates a note with provenance='llm' + source_id. (M4)
- Editing an 'llm' note flips it to 'llm_edited'.                          (here)
- Notes created through MCP get provenance='llm'.                          (M6)
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chunking import join_lines
from app.core.errors import InvalidInput, NotFound
from app.core.papers import get_paper
from app.models import Note, Provenance, note_anchors

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class Anchor:
    paper_id: uuid.UUID
    page: int
    bbox: list[Rect]
    quoted_text: str


@dataclass(frozen=True)
class NoteView:
    id: uuid.UUID
    body: str
    provenance: str
    source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    anchors: list[Anchor]


def edited_provenance(current: str) -> str:
    return Provenance.LLM_EDITED if current == Provenance.LLM else current


def normalize_quote(text: str) -> str:
    """Browser selections keep the PDF's line breaks ("trans-\\nfer"); store reading text."""
    return join_lines(text.splitlines())


def reading_position(note: NoteView, paper_id: uuid.UUID) -> tuple[int, float, float]:
    return min((a.page, r[1], r[0]) for a in note.anchors if a.paper_id == paper_id for r in a.bbox)


async def _get_note(session: AsyncSession, note_id: uuid.UUID) -> Note:
    note = await session.get(Note, note_id)
    if note is None:
        raise NotFound(f"note {note_id} not found")
    return note


async def _with_anchors(session: AsyncSession, notes: list[Note]) -> list[NoteView]:
    rows = await session.execute(select(note_anchors).where(note_anchors.c.note_id.in_([n.id for n in notes])))
    anchors: dict[uuid.UUID, list[Anchor]] = {}
    for row in rows:
        anchor = Anchor(
            paper_id=row.paper_id,
            page=row.page,
            bbox=[tuple(r) for r in row.bbox],
            quoted_text=row.quoted_text or "",
        )
        anchors.setdefault(row.note_id, []).append(anchor)
    return [
        NoteView(
            id=n.id,
            body=n.body,
            provenance=n.provenance,
            source_id=n.source_id,
            created_at=n.created_at,
            updated_at=n.updated_at,
            anchors=anchors.get(n.id, []),
        )
        for n in notes
    ]


async def create_human_note(session: AsyncSession, body: str, anchor: Anchor) -> NoteView:
    paper = await get_paper(session, anchor.paper_id)
    if paper.page_count is not None and not 1 <= anchor.page <= paper.page_count:
        raise InvalidInput(f"page {anchor.page} is outside 1..{paper.page_count}")
    quote = normalize_quote(anchor.quoted_text)
    if not quote:
        raise InvalidInput("an anchor needs the quoted text")

    note = Note(body=body.strip(), provenance=Provenance.HUMAN)
    session.add(note)
    await session.flush()
    await session.execute(
        insert(note_anchors).values(
            note_id=note.id,
            paper_id=anchor.paper_id,
            page=anchor.page,
            bbox=[list(r) for r in anchor.bbox],
            quoted_text=quote,
        )
    )
    await session.commit()
    await session.refresh(note)
    return (await _with_anchors(session, [note]))[0]


async def list_notes_for_paper(session: AsyncSession, paper_id: uuid.UUID) -> list[NoteView]:
    await get_paper(session, paper_id)
    anchored_here = select(note_anchors.c.note_id).where(note_anchors.c.paper_id == paper_id)
    notes = list(await session.scalars(select(Note).where(Note.id.in_(anchored_here))))
    views = await _with_anchors(session, notes)
    return sorted(views, key=lambda v: reading_position(v, paper_id))


async def update_note_body(session: AsyncSession, note_id: uuid.UUID, body: str) -> NoteView:
    note = await _get_note(session, note_id)
    new_body = body.strip()
    if new_body != note.body:
        await session.execute(
            update(Note)
            .where(Note.id == note_id)
            .values(body=new_body, provenance=edited_provenance(note.provenance), updated_at=func.now())
        )
        await session.commit()
        await session.refresh(note)
    return (await _with_anchors(session, [note]))[0]


async def delete_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    await _get_note(session, note_id)
    await session.execute(delete(Note).where(Note.id == note_id))
    await session.commit()
