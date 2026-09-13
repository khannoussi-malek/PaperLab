import asyncio
import uuid
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.chunking import STRATEGY_VERSION, ChunkDraft
from app.core.errors import InvalidInput, NotFound
from app.models import Chunk, Paper, PaperStatus

PDF_MAGIC = b"%PDF-"


async def create_paper(session: AsyncSession, filename: str, data: bytes, pdf_dir: Path) -> Paper:
    if not data.startswith(PDF_MAGIC):
        raise InvalidInput(f"{filename!r} is not a PDF")

    paper_id = uuid.uuid4()
    path = pdf_dir / f"{paper_id}.pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    # Title is a placeholder until extraction (and later enrichment) finds a real one.
    paper = Paper(id=paper_id, title=Path(filename).stem or "untitled", file_path=str(path))
    session.add(paper)
    try:
        await session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    await session.refresh(paper)
    return paper


async def get_paper(session: AsyncSession, paper_id: uuid.UUID) -> Paper:
    paper = await session.get(Paper, paper_id)
    if paper is None:
        raise NotFound(f"paper {paper_id} not found")
    return paper


async def list_papers(session: AsyncSession) -> list[Paper]:
    return list(await session.scalars(select(Paper).order_by(Paper.created_at.desc())))


async def list_chunks(session: AsyncSession, paper_id: uuid.UUID, page: int | None = None) -> list[Chunk]:
    await get_paper(session, paper_id)
    query = select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    if page is not None:
        query = query.where(Chunk.page == page)
    return list(await session.scalars(query))


async def set_status(
    session: AsyncSession, paper_id: uuid.UUID, status: PaperStatus, error: str | None = None, **fields
) -> None:
    """Commits immediately so the UI can watch the pipeline progress."""
    await session.execute(
        update(Paper).where(Paper.id == paper_id).values(status=status, status_error=error, **fields)
    )
    await session.commit()


async def replace_chunks(session: AsyncSession, paper_id: uuid.UUID, drafts: list[ChunkDraft]) -> None:
    """Delete-then-insert in one transaction, so re-running ingestion is idempotent."""
    await session.execute(delete(Chunk).where(Chunk.paper_id == paper_id))
    session.add_all(
        Chunk(
            paper_id=paper_id,
            ordinal=d.ordinal,
            page=d.page,
            bbox=d.bbox,
            section_title=d.section_title,
            text=d.text,
            embed_model=settings.embed_model,
            strategy_ver=STRATEGY_VERSION,
        )
        for d in drafts
    )
    await session.commit()
