"""Manuscript snapshots: text files as of a moment, kept newest-50, restorable."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.errors import Conflict, NotFound
from app.core.manuscript_paths import is_text
from app.models import ManuscriptFile, ManuscriptSnapshot

KEEP = 50
MCP_REASON = "before_mcp"
MCP_KEEP = 20  # Claude's edits are kept apart so a busy session cannot push the owner's snapshots out
AUTOSAVE_EVERY = timedelta(minutes=10)


async def take(session: AsyncSession, manuscript_id: uuid.UUID, reason: str) -> ManuscriptSnapshot:
    if reason == MCP_REASON and await _changed_since_last_snapshot(session, manuscript_id):
        await take(session, manuscript_id, "autosave")  # the owner's latest text, before Claude writes
    rows = await session.execute(
        select(ManuscriptFile.path, ManuscriptFile.text)
        .where(ManuscriptFile.manuscript_id == manuscript_id, ManuscriptFile.text.is_not(None))
    )
    snap = ManuscriptSnapshot(manuscript_id=manuscript_id, reason=reason, files=dict(rows.all()),
                              created_at=func.clock_timestamp())
    session.add(snap)
    await session.flush()
    await session.refresh(snap)
    for is_mcp, keep in ((False, KEEP), (True, MCP_KEEP)):
        group = ManuscriptSnapshot.manuscript_id == manuscript_id
        is_kind = ManuscriptSnapshot.reason == MCP_REASON
        group = group & (is_kind if is_mcp else ~is_kind)
        newest = select(ManuscriptSnapshot.id).where(group) \
            .order_by(ManuscriptSnapshot.created_at.desc(), ManuscriptSnapshot.id).limit(keep)
        await session.execute(delete(ManuscriptSnapshot).where(group, ManuscriptSnapshot.id.not_in(newest)))
    return snap


async def _changed_since_last_snapshot(session: AsyncSession, manuscript_id: uuid.UUID) -> bool:
    """A text file is newer than every snapshot. Claude's writes don't count: `settle` dates its snapshot after them."""
    changed = await session.scalar(select(func.max(ManuscriptFile.updated_at)).where(
        ManuscriptFile.manuscript_id == manuscript_id, ManuscriptFile.text.is_not(None)))
    last = await session.scalar(
        select(func.max(ManuscriptSnapshot.created_at)).where(ManuscriptSnapshot.manuscript_id == manuscript_id))
    return changed is not None and (last is None or changed > last)


async def settle(session: AsyncSession, snap: ManuscriptSnapshot) -> None:
    """Call after the write the snapshot guards: dates the snapshot after it, so the write reads as already covered."""
    await session.execute(update(ManuscriptSnapshot).where(ManuscriptSnapshot.id == snap.id)
                          .values(created_at=func.clock_timestamp()))


async def maybe_autosave(session: AsyncSession, manuscript_id: uuid.UUID, *, now: datetime) -> bool:
    last = await session.scalar(
        select(func.max(ManuscriptSnapshot.created_at)).where(
            ManuscriptSnapshot.manuscript_id == manuscript_id, ManuscriptSnapshot.reason != MCP_REASON))
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
