import uuid

import pytest
from sqlalchemy import select

from app.core import papers
from app.core.chunking import ChunkDraft
from app.core.errors import InvalidInput, NotFound
from app.models import Chunk, Paper, PaperStatus

pytestmark = pytest.mark.anyio

PDF_BYTES = b"%PDF-1.7\n%fake but has the magic header\n"


def draft(ordinal: int, page: int, text: str = "some chunk text") -> ChunkDraft:
    return ChunkDraft(ordinal=ordinal, page=page, bbox=[[1.0, 2.0, 3.0, 4.0]], section_title=None, text=text)


async def test_create_paper_writes_file_and_row(session, tmp_path):
    paper = await papers.create_paper(session, "My Paper.pdf", PDF_BYTES, tmp_path)

    assert paper.title == "My Paper"
    assert paper.status == PaperStatus.UPLOADED
    assert (tmp_path / f"{paper.id}.pdf").read_bytes() == PDF_BYTES
    assert await session.get(Paper, paper.id) is not None


async def test_create_paper_rejects_non_pdf_without_writing(session, tmp_path):
    with pytest.raises(InvalidInput, match="not a PDF"):
        await papers.create_paper(session, "notes.txt", b"hello", tmp_path)
    assert not tmp_path.exists() or not any(tmp_path.iterdir())


async def test_create_paper_removes_file_when_commit_fails(session, tmp_path, monkeypatch):
    async def failing_commit():
        raise RuntimeError("db down")

    monkeypatch.setattr(session, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        await papers.create_paper(session, "paper.pdf", PDF_BYTES, tmp_path)
    assert list(tmp_path.glob("*.pdf")) == []


async def test_get_paper_unknown_raises_not_found(session):
    with pytest.raises(NotFound):
        await papers.get_paper(session, uuid.uuid4())


async def test_replace_chunks_is_idempotent(session, tmp_path):
    paper = await papers.create_paper(session, "paper.pdf", PDF_BYTES, tmp_path)

    await papers.replace_chunks(session, paper.id, [draft(0, 1), draft(1, 1), draft(2, 2)])
    await papers.replace_chunks(session, paper.id, [draft(0, 1), draft(1, 2)])

    rows = (await session.execute(select(Chunk.ordinal, Chunk.page).where(Chunk.paper_id == paper.id))).all()
    assert sorted(rows) == [(0, 1), (1, 2)]


async def test_list_chunks_orders_and_filters_by_page(session, tmp_path):
    paper = await papers.create_paper(session, "paper.pdf", PDF_BYTES, tmp_path)
    await papers.replace_chunks(session, paper.id, [draft(1, 2), draft(0, 1), draft(2, 2)])

    assert [c.ordinal for c in await papers.list_chunks(session, paper.id)] == [0, 1, 2]
    assert [c.ordinal for c in await papers.list_chunks(session, paper.id, page=2)] == [1, 2]
    with pytest.raises(NotFound):
        await papers.list_chunks(session, uuid.uuid4())


async def test_set_status_records_error_and_fields(session, tmp_path):
    paper = await papers.create_paper(session, "paper.pdf", PDF_BYTES, tmp_path)

    await papers.set_status(session, paper.id, PaperStatus.FAILED, error="boom", page_count=7)
    await session.refresh(paper)

    assert (paper.status, paper.status_error, paper.page_count) == ("failed", "boom", 7)
