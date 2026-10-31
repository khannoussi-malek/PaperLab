"""The manuscript operations an outside agent (the MCP) may do, each guarded the way the editor is: the app's path
and size rules, a `base` (the file's `updated_at`) on every change to an existing file, and a `before_mcp` snapshot
in the same transaction as every text write. Every writing function commits on success and rolls back on any error."""

import base64
import binascii
import functools
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscript_history, manuscript_templates, manuscripts, workspaces
from app.core import manuscript_paths as paths
from app.core.errors import Conflict, InvalidInput
from app.models import ManuscriptSnapshot

Base = AwareDatetime  # the tools' `base` type, so server.py imports nothing new
MAX_TITLE = 200


@dataclass(frozen=True)
class FileInfo:
    path: str
    size: int
    kind: str  # "text" | "binary"
    updated_at: AwareDatetime


@dataclass(frozen=True)
class ManuscriptSummary:
    id: uuid.UUID
    title: str
    workspace: str | None
    main_file: str
    compile_status: str
    updated_at: AwareDatetime


@dataclass(frozen=True)
class ManuscriptCreated:
    id: uuid.UUID
    title: str
    workspace: str | None
    main_file: str
    files: list[FileInfo]


@dataclass(frozen=True)
class ManuscriptFiles:
    manuscript_id: uuid.UUID
    title: str
    main_file: str
    files: list[FileInfo]


@dataclass(frozen=True)
class FileText:
    path: str
    text: str
    updated_at: AwareDatetime
    size: int
    total_lines: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Written:
    path: str
    size: int
    updated_at: AwareDatetime
    snapshot_id: uuid.UUID | None


@dataclass(frozen=True)
class Renamed:
    path: str
    new_path: str
    updated_at: AwareDatetime
    snapshot_id: uuid.UUID | None


@dataclass(frozen=True)
class Deleted:
    path: str
    snapshot_id: uuid.UUID | None


@dataclass(frozen=True)
class FigureAdded:
    path: str
    size: int
    updated_at: AwareDatetime


def _committing(fn):
    """Commit once the operation succeeded; roll back on anything else, so no half-done write or snapshot survives."""

    @functools.wraps(fn)
    async def wrapper(session: AsyncSession, *args, **kwargs):
        try:
            result = await fn(session, *args, **kwargs)
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
        return result

    return wrapper


def _info(row) -> FileInfo:
    return FileInfo(
        path=row.path, size=row.size, kind="text" if paths.is_text(row.path) else "binary", updated_at=row.updated_at
    )


def _status(manuscript) -> str:
    """The app's read-time rule: a `running` with no live job behind it reads as failed."""
    return "failed" if manuscripts.interrupted(manuscript, datetime.now(timezone.utc)) else manuscript.compile_status


async def list_manuscripts(session: AsyncSession, workspace: str | None) -> list[ManuscriptSummary]:
    if workspace is None:
        rows = await manuscripts.list_all(session)
    else:
        rows = await manuscripts.list_for(session, workspace_id=await workspaces.by_name(session, workspace))
    names = {view.id: view.name for view in await workspaces.list_workspaces(session)}
    return [
        ManuscriptSummary(
            id=m.id,
            title=m.title,
            workspace=names.get(m.workspace_id),
            main_file=m.main_file,
            compile_status=_status(m),
            updated_at=m.updated_at,
        )
        for m in rows
    ]


@_committing
async def create_manuscript(
    session: AsyncSession, title: str, template: str = "article", workspace: str | None = None
) -> ManuscriptCreated:
    title = title.strip()
    if not 1 <= len(title) <= MAX_TITLE:
        raise InvalidInput("bad_title")
    if template not in manuscript_templates.TEMPLATES:
        raise InvalidInput("unknown_template", available=list(manuscript_templates.TEMPLATES))
    workspace_id = None if workspace is None else await workspaces.by_name(session, workspace)
    manuscript = await manuscripts.create(session, title=title, template=template, workspace_id=workspace_id)
    files = [_info(f) for f in await manuscripts.files(session, manuscript.id)]
    return ManuscriptCreated(
        id=manuscript.id,
        title=title,
        workspace=workspace and workspace.strip(),
        main_file=manuscript.main_file,
        files=files,
    )


async def list_files(session: AsyncSession, mid: uuid.UUID) -> ManuscriptFiles:
    manuscript = await manuscripts.get(session, mid)
    return ManuscriptFiles(
        manuscript_id=mid,
        title=manuscript.title,
        main_file=manuscript.main_file,
        files=[_info(f) for f in await manuscripts.files(session, mid)],
    )


async def _text_row(session: AsyncSession, mid: uuid.UUID, path: str):
    row = await manuscripts.read(session, mid, path)
    if row.text is None:
        raise InvalidInput("binary_file")
    return row


async def read_file(
    session: AsyncSession, mid: uuid.UUID, path: str, start_line: int = 1, end_line: int | None = None
) -> FileText:
    row = await _text_row(session, mid, path)
    lines = row.text.splitlines(keepends=True)
    end = len(lines) if end_line is None else min(end_line, len(lines))
    if start_line < 1 or start_line > max(end, 1) or (end_line is not None and start_line > end_line):
        raise InvalidInput("bad_line_range")
    return FileText(
        path=path,
        text="".join(lines[start_line - 1 : end]),
        updated_at=row.updated_at,
        size=row.size,
        total_lines=len(lines),
        start_line=start_line,
        end_line=end,
    )


async def _snapshot_id(session: AsyncSession, mid: uuid.UUID) -> uuid.UUID | None:
    """This transaction's `before_mcp` snapshot: the newest one."""
    return await session.scalar(
        select(ManuscriptSnapshot.id)
        .where(ManuscriptSnapshot.manuscript_id == mid, ManuscriptSnapshot.reason == manuscript_history.MCP_REASON)
        .order_by(ManuscriptSnapshot.created_at.desc(), ManuscriptSnapshot.id)
        .limit(1)
    )


async def _written(session: AsyncSession, mid: uuid.UUID, row) -> Written:
    return Written(
        path=row.path, size=row.size, updated_at=row.updated_at, snapshot_id=await _snapshot_id(session, mid)
    )


def _require_base(row, base: Base) -> None:
    """The base must be exactly the file's `updated_at` (what read_file returned): a guessed one is not a read."""
    if row.updated_at != base:
        raise Conflict("file_changed", updated_at=row.updated_at)


@_committing
async def create_file(session: AsyncSession, mid: uuid.UUID, path: str, text: str) -> Written:
    try:
        row = await manuscripts.save_text(
            session, mid, path, text, base=None, snapshot=manuscript_history.MCP_REASON
        )
    except IntegrityError:  # a racing create or rename of the same new path committed first
        raise Conflict("file_exists") from None
    return await _written(session, mid, row)


@_committing
async def write_file(session: AsyncSession, mid: uuid.UUID, path: str, text: str, base: Base) -> Written:
    if not paths.is_text(paths.validate_path(path)):
        raise InvalidInput("unsupported_file_type")
    _require_base(await _text_row(session, mid, path), base)
    row = await manuscripts.save_text(session, mid, path, text, base=base, snapshot=manuscript_history.MCP_REASON)
    return await _written(session, mid, row)


def apply_edit(text: str, old: str, new: str) -> str:
    if not old:
        raise InvalidInput("empty_old_text")
    count = text.count(old)
    if count == 0:
        raise Conflict("no_match")
    if count > 1:
        raise Conflict("ambiguous_match", count=count)
    return text.replace(old, new, 1)


@_committing
async def edit_file(
    session: AsyncSession, mid: uuid.UUID, path: str, old_text: str, new_text: str, base: Base
) -> Written:
    paths.validate_path(path)  # a hostile path answers its own code, not unknown_file
    row = await _text_row(session, mid, path)
    if row.updated_at > base:
        raise Conflict("file_changed", updated_at=row.updated_at)
    # The recheck under the row lock is against the row the new text was computed from, not the caller's (maybe
    # newer) base: an owner save landing since our unlocked read is refused, never overwritten.
    saved = await manuscripts.save_text(
        session,
        mid,
        path,
        apply_edit(row.text, old_text, new_text),
        base=row.updated_at,
        snapshot=manuscript_history.MCP_REASON,
    )
    return await _written(session, mid, saved)


@_committing
async def rename_file(session: AsyncSession, mid: uuid.UUID, path: str, new_path: str, base: Base) -> Renamed:
    paths.validate_path(new_path)
    paths.validate_path(path)
    _require_base(await _text_row(session, mid, path), base)
    if path == (await manuscripts.get(session, mid)).main_file:
        raise Conflict("main_file")  # a restore of the snapshot would fail without the new main file
    try:
        row = await manuscripts.rename(
            session, mid, path, new_path, base=base, snapshot=manuscript_history.MCP_REASON
        )
    except IntegrityError:  # a racing create of the new path committed first
        raise Conflict("file_exists") from None
    return Renamed(
        path=path, new_path=row.path, updated_at=row.updated_at, snapshot_id=await _snapshot_id(session, mid)
    )


@_committing
async def delete_file(session: AsyncSession, mid: uuid.UUID, path: str, base: Base) -> Deleted:
    paths.validate_path(path)
    _require_base(await _text_row(session, mid, path), base)
    await manuscripts.remove(session, mid, path, base=base, snapshot=manuscript_history.MCP_REASON)
    return Deleted(path=path, snapshot_id=await _snapshot_id(session, mid))


@_committing
async def add_figure(session: AsyncSession, mid: uuid.UUID, path: str, data_base64: str) -> FigureAdded:
    paths.validate_path(path)
    if paths.is_text(path):
        raise InvalidInput("unsupported_file_type")
    try:
        data = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidInput("bad_base64") from None
    try:
        row = await manuscripts.put_binary(session, mid, path, data, create_only=True)  # never overwrite a binary
    except IntegrityError:  # a racing add of the same new path committed first
        raise Conflict("file_exists") from None
    return FigureAdded(path=path, size=row.size, updated_at=row.updated_at)
