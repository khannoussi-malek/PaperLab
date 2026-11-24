"""The MCP tool that adds a PDF the client already holds, sent as base64."""

import asyncio
import base64
import binascii
import math
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.papers import papers
from app.core.papers.pipeline import workspace_id
from app.core.papers.pipeline_add import AddPaperResult, _attach
from app.core.platform import queue
from app.core.workspaces import tags, workspaces
from app.domain.doi import normalize_doi
from app.domain.errors import InvalidInput
from app.models import Paper, PaperStatus

MAX_UPLOAD_PDF_BYTES = 30 * 1024 * 1024  # decoded, as the app's upload allows
MAX_UPLOAD_BASE64_CHARS = 4 * math.ceil(MAX_UPLOAD_PDF_BYTES / 3) + 4  # refused before decoding allocates anything


def _decode_pdf(pdf_base64: str) -> bytes:
    if len(pdf_base64) > MAX_UPLOAD_BASE64_CHARS:
        raise InvalidInput("pdf_too_large", max_mb=MAX_UPLOAD_PDF_BYTES // 1024 // 1024)
    try:
        data = base64.b64decode(pdf_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidInput("invalid_base64") from exc
    if len(data) > MAX_UPLOAD_PDF_BYTES:
        raise InvalidInput("pdf_too_large", max_mb=MAX_UPLOAD_PDF_BYTES // 1024 // 1024)
    if not data.startswith(papers.PDF_MAGIC):
        raise InvalidInput("not_a_pdf")
    return data


async def upload_paper(
    session: AsyncSession,
    workspace: str,
    filename: str,
    pdf_base64: str,
    doi: str | None = None,
    tag_names: list[str] | None = None,
) -> AddPaperResult:
    """The twin of POST /api/papers for a PDF Claude holds: filed in `workspace`, tagged, ingest queued. A `doi` already
    in the library reuses that paper (no second copy); otherwise it is kept on the new paper as a locked field.
    Everything is checked before the first write."""
    ws = await workspace_id(session, workspace)
    await workspaces.require_writable(session, ws)
    names = [tags.normalize(name) for name in tag_names or []]
    clean_doi = None
    if doi is not None and (clean_doi := normalize_doi(doi)) is None:
        raise InvalidInput("invalid_doi")
    data = _decode_pdf(pdf_base64)
    existing = await session.scalar(select(Paper).where(func.lower(Paper.doi) == clean_doi)) if clean_doi else None
    raced = None
    if existing and not existing.has_pdf:  # saved without one: the upload becomes its PDF
        paper, status = existing, "queued"
        raced = await _attach(session, existing, data, "manual")
    elif existing and existing.file_path and existing.status == PaperStatus.FAILED:  # a retry, as _add_found does
        paper, status = existing, "queued"
        await asyncio.to_thread(Path(paper.file_path).write_bytes, data)  # the upload replaces the broken file
        await papers.set_status(session, paper.id, PaperStatus.UPLOADED)
    elif existing:
        paper, status = existing, "already_in_library"
    else:
        prefill = {"doi": clean_doi, "manual_fields": ["doi"]} if clean_doi else None
        paper, status = await papers.create_paper(session, filename, data, settings.pdf_dir, prefill=prefill), "queued"
    await workspaces.add_paper(session, ws, paper.id)
    for name in names:
        await tags.tag_papers(session, ws, name, paper_ids=[paper.id])
    if status == "queued" and raced is None:
        await queue.enqueue("ingest_paper", str(paper.id))
    return AddPaperResult(status=raced or status, paper_id=paper.id, title=paper.title)
