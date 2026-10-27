"""Manuscript snapshots: text files as of a moment, kept newest-50, restorable."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.errors import Conflict, NotFound
from app.core.manuscript_paths import is_text
from app.models import ManuscriptFile, ManuscriptSnapshot

KEEP = 50
AUTOSAVE_EVERY = timedelta(minutes=10)


async def take(session: AsyncSession, manuscript_id: uuid.UUID, reason: str) -> ManuscriptSnapshot:
    rows = await session.execute(
        select(ManuscriptFile.path, ManuscriptFile.text)
        .where(ManuscriptFile.manuscript_id == manuscript_id, ManuscriptFile.text.is_not(None))
    )
    snap = ManuscriptSnapshot(manuscript_id=manuscript_id, reason=reason, files=dict(rows.all()),
                              created_at=func.clock_timestamp())
    session.add(snap)
    await session.flush()
    await session.refresh(snap)
    newest = select(ManuscriptSnapshot.id).where(ManuscriptSnapshot.manuscript_id == manuscript_id) \
        .order_by(ManuscriptSnapshot.created_at.desc(), ManuscriptSnapshot.id).limit(KEEP)
    await session.execute(delete(ManuscriptSnapshot).where(
        ManuscriptSnapshot.manuscript_id == manuscript_id, ManuscriptSnapshot.id.not_in(newest)))
    return snap


async def maybe_autosave(session: AsyncSession, manuscript_id: uuid.UUID, *, now: datetime) -> bool:
    last = await session.scalar(
        select(func.max(ManuscriptSnapshot.created_at)).where(ManuscriptSnapshot.manuscript_id == manuscript_id))
    if last is not None and now - last < AUTOSAVE_EVERY:
        return False
    await take(session, manuscript_id, "autosave")
    return True


async def list_(session: AsyncSession, manuscript_id: uuid.UUID) -> list[ManuscriptSnapshot]:
    result = await session.scalars(
        select(ManuscriptSnapshot).where(ManuscriptSnapshot.manuscript_id == manuscript_id)
        .order_by(ManuscriptSnapshot.created_at.desc(), ManuscriptSnapshot.id))
    return list(result)


async def get(session: AsyncSession, snapshot_id: uuid.UUID) -> ManuscriptSnapshot:
    snap = await session.get(ManuscriptSnapshot, snapshot_id)
    if snap is None:
        raise NotFound("unknown_snapshot")
    return snap


async def restore(session: AsyncSession, manuscript_id: uuid.UUID, snapshot_id: uuid.UUID) -> None:
    """Make the text files exactly the snapshot's; binaries stay."""
    manuscript = await manuscripts.get(session, manuscript_id)
    snap = await get(session, snapshot_id)
    if snap.manuscript_id != manuscript_id:
        raise NotFound("unknown_snapshot")
    if manuscript.main_file not in snap.files:
        raise Conflict("main_file")
    await take(session, manuscript_id, "before_restore")
    for f in await manuscripts.files(session, manuscript_id):
        if is_text(f.path) and f.path not in snap.files:  # the main file is in the snapshot, so it stays
            await manuscripts.remove(session, manuscript_id, f.path)
    for path, text in snap.files.items():
        current = await manuscripts.get_text(session, manuscript_id, path)
        if current != text:  # an untouched file keeps its updated_at, so an open editor sees no conflict
            await manuscripts.upsert_text(session, manuscript_id, path, text)
