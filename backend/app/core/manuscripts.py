"""Manuscripts and their files, stored in Postgres. Writes check the size caps and bump `updated_at`."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select
from sqlalchemy import update as update_rows
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.config import settings
from app.core import manuscript_history, manuscript_templates, queue
from app.core import manuscript_paths as paths
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.latex_compile import COMPILE_TIMEOUT
from app.models import Manuscript, ManuscriptFile, Workspace

_UNSET = object()  # "leave this field as it is"; workspace_id=None moves the manuscript out of its workspace
_NOW = func.clock_timestamp()  # not now(): that is the transaction's start, so two saves in one transaction tie
_META = load_only(ManuscriptFile.id, ManuscriptFile.manuscript_id, ManuscriptFile.path, ManuscriptFile.size,
                  ManuscriptFile.updated_at)


async def _check_workspace(session: AsyncSession, workspace_id: uuid.UUID | None) -> None:
    if workspace_id is not None and await session.get(Workspace, workspace_id) is None:
        raise NotFound("unknown_workspace")


async def create(session: AsyncSession, *, title: str, template: str, workspace_id: uuid.UUID | None) -> Manuscript:
    contents = manuscript_templates.files(template)
    await _check_workspace(session, workspace_id)
    manuscript = Manuscript(title=title, workspace_id=workspace_id)
    session.add(manuscript)
    await session.flush()
    for path, text in contents.items():
        await upsert_text(session, manuscript.id, path, text)
    await session.refresh(manuscript)
    return manuscript


async def get(session: AsyncSession, manuscript_id: uuid.UUID) -> Manuscript:
    manuscript = await session.get(Manuscript, manuscript_id, populate_existing=True)
    if manuscript is None:
        raise NotFound("unknown_manuscript")
    return manuscript


async def list_for(session: AsyncSession, *, workspace_id: uuid.UUID | None) -> list[Manuscript]:
    where = Manuscript.workspace_id.is_(None) if workspace_id is None else Manuscript.workspace_id == workspace_id
    return list(await session.scalars(select(Manuscript).where(where).order_by(Manuscript.updated_at.desc())))


async def update(session: AsyncSession, manuscript_id: uuid.UUID, *, title=_UNSET, workspace_id=_UNSET,
                 main_file=_UNSET, checklist=_UNSET) -> Manuscript:
    manuscript = await get(session, manuscript_id)
    if workspace_id is not _UNSET:
        await _check_workspace(session, workspace_id)
    if main_file is not _UNSET:
        if not main_file.endswith(".tex"):
            raise InvalidInput("main_file_not_tex")
        if await _file(session, manuscript_id, main_file) is None:
            raise NotFound("unknown_file")
    changes = {k: v for k, v in (("title", title), ("workspace_id", workspace_id), ("main_file", main_file),
                                 ("checklist", checklist)) if v is not _UNSET}
    await session.execute(update_rows(Manuscript).where(Manuscript.id == manuscript.id)
                          .values(**changes, updated_at=_NOW))
    return await get(session, manuscript_id)


async def delete(session: AsyncSession, manuscript_id: uuid.UUID) -> None:
    await get(session, manuscript_id)
    await session.execute(delete_rows(Manuscript).where(Manuscript.id == manuscript_id))


async def files(session: AsyncSession, manuscript_id: uuid.UUID) -> list[ManuscriptFile]:
    await get(session, manuscript_id)
    rows = await session.scalars(select(ManuscriptFile).options(_META)
                                 .where(ManuscriptFile.manuscript_id == manuscript_id).order_by(ManuscriptFile.path))
    return list(rows)


async def read(session: AsyncSession, manuscript_id: uuid.UUID, path: str) -> ManuscriptFile:
    await get(session, manuscript_id)
    row = await _file(session, manuscript_id, path)
    if row is None:
        raise NotFound("unknown_file")
    return row


async def get_text(session: AsyncSession, manuscript_id: uuid.UUID, path: str) -> str | None:
    """A file's text, or None when it is missing or binary."""
    return await session.scalar(select(ManuscriptFile.text).where(
        ManuscriptFile.manuscript_id == manuscript_id, ManuscriptFile.path == path))


async def _file(session, manuscript_id, path, *, lock=False) -> ManuscriptFile | None:
    query = select(ManuscriptFile).where(ManuscriptFile.manuscript_id == manuscript_id, ManuscriptFile.path == path)
    return await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))


async def _check_caps(session, manuscript_id, size: int, limit: int, existing: ManuscriptFile | None) -> None:
    if size > limit:
        raise Conflict("file_too_large", limit=limit)
    total, count = (await session.execute(
        select(func.coalesce(func.sum(ManuscriptFile.size), 0), func.count())
        .where(ManuscriptFile.manuscript_id == manuscript_id))).one()
    if existing is not None:
        total -= existing.size
        count -= 1
    if total + size > paths.MAX_TOTAL:
        raise Conflict("manuscript_too_large", limit=paths.MAX_TOTAL)
    if count + 1 > paths.MAX_FILES:
        raise Conflict("too_many_files", limit=paths.MAX_FILES)


async def _store(session, manuscript_id, path, row: ManuscriptFile | None, **content) -> ManuscriptFile:
    """Insert or overwrite one file row, then bump the manuscript."""
    size = len(content["text"].encode()) if content["text"] is not None else len(content["data"])
    if row is None:
        row = ManuscriptFile(manuscript_id=manuscript_id, path=path, size=size, updated_at=_NOW, **content)
        session.add(row)
    else:
        await session.execute(update_rows(ManuscriptFile).where(ManuscriptFile.id == row.id)
                              .values(size=size, updated_at=_NOW, **content))
    await session.execute(update_rows(Manuscript).where(Manuscript.id == manuscript_id).values(updated_at=_NOW))
    await session.flush()
    await session.refresh(row)
    return row


def _require_text(path: str) -> None:
    if not paths.is_text(paths.validate_path(path)):
        raise InvalidInput("unsupported_file_type")


async def upsert_text(session: AsyncSession, manuscript_id: uuid.UUID, path: str, text: str) -> ManuscriptFile:
    """Write a text file with no stale check and no autosave (a template, a restore)."""
    await get(session, manuscript_id)
    _require_text(path)
    row = await _file(session, manuscript_id, path, lock=True)
    await _check_caps(session, manuscript_id, len(text.encode()), paths.MAX_TEXT, row)
    return await _store(session, manuscript_id, path, row, text=text, data=None)


async def save_text(session: AsyncSession, manuscript_id: uuid.UUID, path: str, text: str, *,
                    base: datetime | None) -> ManuscriptFile:
    await get(session, manuscript_id)
    _require_text(path)
    row = await _file(session, manuscript_id, path, lock=True)
    if base is None and row is not None:
        raise Conflict("file_exists")
    if base is not None and row is None:
        raise NotFound("unknown_file")
    if base is not None and row.updated_at > base:
        raise Conflict("file_changed", updated_at=row.updated_at)
    await _check_caps(session, manuscript_id, len(text.encode()), paths.MAX_TEXT, row)
    saved = await _store(session, manuscript_id, path, row, text=text, data=None)
    await manuscript_history.maybe_autosave(session, manuscript_id, now=datetime.now(timezone.utc))
    return saved


async def put_binary(session: AsyncSession, manuscript_id: uuid.UUID, path: str, data: bytes) -> ManuscriptFile:
    await get(session, manuscript_id)
    if paths.is_text(paths.validate_path(path)):
        raise InvalidInput("unsupported_file_type")
    row = await _file(session, manuscript_id, path, lock=True)
    await _check_caps(session, manuscript_id, len(data), paths.MAX_BINARY, row)
    return await _store(session, manuscript_id, path, row, text=None, data=data)


async def rename(session: AsyncSession, manuscript_id: uuid.UUID, path: str, new_path: str) -> ManuscriptFile:
    manuscript = await get(session, manuscript_id)
    paths.validate_path(new_path)
    row = await _file(session, manuscript_id, path, lock=True)
    if row is None:
        raise NotFound("unknown_file")
    if paths.is_text(path) != paths.is_text(new_path):
        raise InvalidInput("unsupported_file_type")
    if await _file(session, manuscript_id, new_path) is not None:
        raise Conflict("file_exists")
    await session.execute(update_rows(ManuscriptFile).where(ManuscriptFile.id == row.id)
                          .values(path=new_path, updated_at=_NOW))
    changes = {"main_file": new_path} if manuscript.main_file == path else {}
    await session.execute(update_rows(Manuscript).where(Manuscript.id == manuscript_id)
                          .values(updated_at=_NOW, **changes))
    await session.refresh(row)
    return row


async def remove(session: AsyncSession, manuscript_id: uuid.UUID, path: str) -> None:
    manuscript = await get(session, manuscript_id)
    if await _file(session, manuscript_id, path, lock=True) is None:
        raise NotFound("unknown_file")
    if path == manuscript.main_file:
        raise Conflict("main_file")
    await session.execute(delete_rows(ManuscriptFile).where(
        ManuscriptFile.manuscript_id == manuscript_id, ManuscriptFile.path == path))
    await session.execute(update_rows(Manuscript).where(Manuscript.id == manuscript_id).values(updated_at=_NOW))


def pdf_path(manuscript_id: uuid.UUID) -> Path:
    return settings.pdf_dir / "manuscripts" / f"{manuscript_id}.pdf"


async def request_compile(session: AsyncSession, manuscript_id: uuid.UUID, *, now: datetime) -> str:
    """Queue a compile, or ask the running one for another pass. Returns "queued" or "again"."""
    manuscript = await session.scalar(select(Manuscript).where(Manuscript.id == manuscript_id)
                                      .with_for_update().execution_options(populate_existing=True))
    if manuscript is None:
        raise NotFound("unknown_manuscript")
    started = manuscript.compile_started_at
    if manuscript.compile_status == "running" and started and now - started < timedelta(seconds=COMPILE_TIMEOUT + 60):
        manuscript.compile_requested = True
        await session.commit()
        return "again"
    manuscript.compile_status, manuscript.compile_started_at = "running", now
    await session.commit()
    try:
        await queue.enqueue("compile_manuscript", str(manuscript_id))
    except Exception:
        manuscript.compile_status = "failed"  # no job will run: don't leave it `running`
        await session.commit()
        raise
    return "queued"
