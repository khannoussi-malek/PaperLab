"""The MCP activity log and the owner's switch for changes from Claude (M36). One row per tool call, capped at
ACTIVITY_CAP rows; one settings row. Local only: nothing here leaves the machine."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import McpActivity, McpSettings

ACTIVITY_CAP = 1000
TEXT_CAP = 200  # a string argument longer than this is cut to this many characters and "…"
SUMMARY_CAP = 500  # the whole summary, "…" included
UPLOAD_KEYS = frozenset({"pdf_base64"})  # upload_paper's file content: stored as its size, never as text
ELLIPSIS = "…"
WRITES_DISABLED = {
    "error": "writes_disabled",
    "detail": "The owner has turned off changes from Claude in PaperLab's Connect Claude page.",
}


@dataclass(frozen=True)
class ActivityRow:
    at: datetime
    tool: str
    arguments: str
    outcome: str
    duration_ms: int
    is_write: bool


def _cut(text: str, keep: int) -> str:
    return text if len(text) <= keep else text[:keep] + ELLIPSIS


def _shrink(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _upload_size(val) if key in UPLOAD_KEYS and isinstance(val, str) else _shrink(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_shrink(item) for item in value]
    if isinstance(value, str):
        return _cut(value, TEXT_CAP)
    return value


def _upload_size(encoded: str) -> str:
    """The decoded size of a base64 string with no line breaks: 3 bytes per 4 characters, less the padding."""
    return f"<{len(encoded.rstrip('=')) * 3 // 4} bytes>"


def summarise(arguments: dict) -> str:
    """The arguments as compact JSON: long strings cut, uploads replaced by their size, the whole capped."""
    text = json.dumps(_shrink(arguments), ensure_ascii=False, separators=(",", ":"), default=str)
    return _cut(text, SUMMARY_CAP - len(ELLIPSIS))


async def record(
    session: AsyncSession, *, tool: str, arguments: dict, outcome: str, duration_ms: int, is_write: bool
) -> None:
    """Adds one row and, in the same transaction, deletes the oldest rows beyond the cap."""
    session.add(
        McpActivity(
            at=datetime.now(timezone.utc),
            tool=tool,
            arguments=summarise(arguments),
            outcome=outcome,
            duration_ms=duration_ms,
            is_write=is_write,
        )
    )
    await session.flush()
    newest = select(McpActivity.id).order_by(McpActivity.at.desc()).limit(ACTIVITY_CAP)
    await session.execute(delete(McpActivity).where(McpActivity.id.not_in(newest)))
    await session.commit()


async def writes_enabled(session: AsyncSession) -> bool:
    row = await session.get(McpSettings, True, populate_existing=True)
    return row is None or row.writes_enabled  # no row yet: the default, on


async def set_writes_enabled(session: AsyncSession, on: bool) -> bool:
    upsert = pg_insert(McpSettings).values(id=True, writes_enabled=on)
    await session.execute(upsert.on_conflict_do_update(index_elements=[McpSettings.id], set_={"writes_enabled": on}))
    await session.commit()
    return on


async def recent(session: AsyncSession, limit: int = 100) -> list[ActivityRow]:
    rows = await session.scalars(select(McpActivity).order_by(McpActivity.at.desc()).limit(limit))
    return [ActivityRow(row.at, row.tool, row.arguments, row.outcome, row.duration_ms, row.is_write) for row in rows]


async def clear(session: AsyncSession) -> int:
    removed = await session.execute(delete(McpActivity))
    await session.commit()
    return removed.rowcount
