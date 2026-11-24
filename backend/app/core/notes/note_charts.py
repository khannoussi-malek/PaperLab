"""Notes on charts: a note made from a chart, and attaching or detaching a chart on a note."""

import uuid

from sqlalchemy import delete, func, insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notes.notes import Anchor, NoteView, _get_note, _link, _view
from app.domain.errors import InvalidInput, NotFound
from app.models import Chart, Note, Provenance, note_anchors, note_charts


async def _get_chart(session: AsyncSession, chart_id: uuid.UUID) -> Chart:
    chart = await session.get(Chart, chart_id)
    if chart is None:
        raise NotFound(f"chart {chart_id} not found")
    return chart


async def attach_chart(session: AsyncSession, note_id: uuid.UUID, chart_id: uuid.UUID) -> NoteView:
    """Shows a chart in a note. Attaching twice is a no-op."""
    note = await _get_note(session, note_id)
    await _get_chart(session, chart_id)
    await session.execute(pg_insert(note_charts).values(note_id=note_id, chart_id=chart_id).on_conflict_do_nothing())
    await session.execute(update(Note).where(Note.id == note_id).values(updated_at=func.now()))
    await session.commit()
    return await _view(session, note)


async def detach_chart(session: AsyncSession, note_id: uuid.UUID, chart_id: uuid.UUID) -> NoteView:
    """Stops showing a chart in a note. Detaching a chart the note doesn't show is a no-op."""
    note = await _get_note(session, note_id)
    removed = await session.execute(
        delete(note_charts).where(note_charts.c.note_id == note_id, note_charts.c.chart_id == chart_id)
    )
    if removed.rowcount:
        await session.execute(update(Note).where(Note.id == note_id).values(updated_at=func.now()))
    await session.commit()
    return await _view(session, note)


async def create_chart_note(session: AsyncSession, chart_id: uuid.UUID, anchors: list[Anchor]) -> NoteView:
    """An empty 'human' note showing the chart, anchored where its data sits in each paper, so it appears in every
    source paper's notes. The anchors come from core/notes/charts.py's chart_anchors."""
    await _get_chart(session, chart_id)
    if not anchors:
        raise InvalidInput("a note needs at least one anchor")
    note = Note(body="", provenance=Provenance.HUMAN)
    session.add(note)
    await session.flush()
    # note_anchors' PK is (note_id, paper_id, page, bbox): one anchor per spot.
    rows: dict[tuple, dict] = {}
    for a in anchors:
        key = (a.paper_id, a.page, tuple(tuple(r) for r in a.bbox))
        rows.setdefault(key, {"note_id": note.id, "paper_id": a.paper_id, "page": a.page,
                              "bbox": [list(r) for r in a.bbox], "quoted_text": a.quoted_text})  # fmt: skip
    await _link(session, note.id, [row["paper_id"] for row in rows.values()])
    await session.execute(insert(note_anchors), list(rows.values()))
    await session.execute(insert(note_charts).values(note_id=note.id, chart_id=chart_id))
    await session.commit()
    return await _view(session, note)
