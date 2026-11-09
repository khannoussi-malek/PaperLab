"""Loads what the checks may read, once, and runs them off the event loop. Read-only: nothing is written or committed."""

import asyncio
import uuid
from datetime import datetime, timezone
from types import MappingProxyType

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.manuscript_checks.base import CheckContext, Cost, ManuscriptInfo
from app.core.manuscript_checks.registry import REGISTRY, CheckRun, run_selected, select
from app.core.manuscript_missing_keys import known_keys, load_texts


async def load_context(session: AsyncSession, mid: uuid.UUID) -> CheckContext:
    manuscript = await manuscripts.get(session, mid)
    files = await load_texts(session, mid)
    pdf = manuscripts.pdf_path(mid)
    status, _, _ = manuscripts.read_state(manuscript, datetime.now(timezone.utc))  # a dead `running` reads as failed
    info = ManuscriptInfo(str(mid), manuscript.main_file, status, manuscript.compiled_at, manuscript.compile_log,
                          pdf if pdf.exists() else None, manuscript.updated_at)
    return CheckContext(MappingProxyType(dict(files)), frozenset(await known_keys(session, manuscript, files)), info)


async def run_checks(session: AsyncSession, mid: uuid.UUID, names: list[str] | None = None,
                     cost: Cost | None = None) -> CheckRun:
    checks = select(names, cost, REGISTRY)  # a bad name fails before any query
    ctx = await load_context(session, mid)
    return await asyncio.to_thread(run_selected, ctx, checks)
