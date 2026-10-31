"""Compile a manuscript and read the result and the PDF's text, for an outside agent (the MCP). The manuscript row holds
the one current result; `status` is `running` from the request until the worker stores it."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pymupdf
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscripts
from app.core.errors import InvalidInput, NotFound
from app.models import Manuscript

MAX_ERRORS = 50
LOG_TAIL = 3_000
MAX_CHARS = 40_000


@dataclass(frozen=True)
class CompileRequested:
    state: str  # "queued" | "again"
    status: str
    started_at: datetime | None


@dataclass(frozen=True)
class CompileError:
    file: str | None
    line: int | None
    message: str
    kind: str  # error | warning | package_missing


@dataclass(frozen=True)
class PdfInfo:
    available: bool
    page_count: int | None
    from_latest_compile: bool


@dataclass(frozen=True)
class CompileView:
    manuscript_id: uuid.UUID
    status: str  # never | running | ok | failed
    finished: bool
    again: bool
    started_at: datetime | None
    compiled_at: datetime | None
    errors: list[CompileError]
    errors_total: int
    friendly: str | None
    log_tail: str | None
    pdf: PdfInfo


@dataclass(frozen=True)
class PdfPage:
    page: int
    text: str


@dataclass(frozen=True)
class PdfText:
    manuscript_id: uuid.UUID
    page_count: int
    first_page: int
    last_page: int
    pages: list[PdfPage]
    truncated: bool
    next_page: int | None
    from_latest_compile: bool


async def compile_manuscript(session: AsyncSession, mid: uuid.UUID) -> CompileRequested:
    now = datetime.now(timezone.utc)
    state = await manuscripts.request_compile(session, mid, now=now)  # the only way a compile is queued
    manuscript = await manuscripts.get(session, mid)
    return CompileRequested(state, manuscript.compile_status, manuscript.compile_started_at)


def _page_count(path) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


async def _pdf_info(mid: uuid.UUID, status: str) -> PdfInfo:
    path = manuscripts.pdf_path(mid)
    if not path.exists():
        return PdfInfo(False, None, False)
    try:
        count = await asyncio.to_thread(_page_count, path)
    except Exception:  # a corrupt file is still "there"; read_pdf_text reports it
        count = None
    return PdfInfo(True, count, status == "ok")


def _view(manuscript: Manuscript, status, friendly, again, pdf: PdfInfo, include_log: bool) -> CompileView:
    errors = [
        CompileError(e.get("file"), e.get("line"), e.get("message", ""), e.get("kind", "error"))
        for e in manuscript.compile_errors[:MAX_ERRORS]
    ]
    log = manuscript.compile_log or ""
    return CompileView(
        manuscript.id,
        status,
        status in ("ok", "failed"),
        again,
        manuscript.compile_started_at,
        manuscript.compiled_at,
        errors,
        len(manuscript.compile_errors),
        friendly,
        log[-LOG_TAIL:] if status == "failed" or include_log else None,
        pdf,
    )


async def get_compile_result(session: AsyncSession, mid: uuid.UUID, include_log: bool = False) -> CompileView:
    manuscript = await manuscripts.get(session, mid)
    status, friendly, again = manuscripts.read_state(manuscript, datetime.now(timezone.utc))
    return _view(manuscript, status, friendly, again, await _pdf_info(mid, status), include_log)


def _read_pages(path, first: int, last: int | None):
    """(page_count, [(page, text)...]) for first..last (1-based, inclusive), stopping before the page that would pass
    the cap, with a single page over the cap cut. Returns (count, pages, last, truncated, next_page)."""
    with pymupdf.open(path) as doc:
        count = doc.page_count
        last = count if last is None else last
        if first < 1 or first > last or last > count:
            raise InvalidInput("bad_page_range")
        pages, used, truncated, next_page = [], 0, False, None
        for number in range(first, last + 1):
            text = doc[number - 1].get_text()
            if used + len(text) > MAX_CHARS:
                if pages:  # never split a page: carry on from this one
                    next_page = number
                    break
                text, truncated = text[:MAX_CHARS], True
                next_page = number + 1 if number < last else None
            pages.append(PdfPage(number, text))
            used += len(text)
            if truncated:
                break
        return count, pages, pages[-1].page, truncated, next_page


async def read_pdf_text(
    session: AsyncSession, mid: uuid.UUID, first_page: int = 1, last_page: int | None = None
) -> PdfText:
    manuscript = await manuscripts.get(session, mid)
    path = manuscripts.pdf_path(mid)
    if not path.exists():
        raise NotFound("no_pdf")
    status = manuscripts.read_state(manuscript, datetime.now(timezone.utc))[0]
    try:
        count, pages, last, truncated, next_page = await asyncio.to_thread(_read_pages, path, first_page, last_page)
    except InvalidInput:
        raise
    except Exception as error:
        raise InvalidInput("unreadable_pdf") from error
    return PdfText(mid, count, first_page, last, pages, truncated, next_page, status == "ok")
