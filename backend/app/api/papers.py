import uuid

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import papers
from app.db import get_session
from app.schemas.papers import ChunkOut, PaperOut

router = APIRouter(prefix="/api/papers", tags=["papers"])


async def _enqueue_ingest(request: Request, paper_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("ingest_paper", str(paper_id))


@router.post("", status_code=201)
async def upload_paper(
    file: UploadFile, request: Request, session: AsyncSession = Depends(get_session)
) -> PaperOut:
    paper = await papers.create_paper(session, file.filename or "untitled.pdf", await file.read(), settings.pdf_dir)
    await _enqueue_ingest(request, paper.id)
    return paper


@router.get("")
async def list_papers(session: AsyncSession = Depends(get_session)) -> list[PaperOut]:
    return await papers.list_papers(session)


@router.get("/{paper_id}")
async def get_paper(paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> PaperOut:
    return await papers.get_paper(session, paper_id)


@router.get("/{paper_id}/chunks")
async def list_chunks(
    paper_id: uuid.UUID, page: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[ChunkOut]:
    return await papers.list_chunks(session, paper_id, page)


@router.post("/{paper_id}/reingest", status_code=202)
async def reingest_paper(
    paper_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> PaperOut:
    paper = await papers.get_paper(session, paper_id)
    await _enqueue_ingest(request, paper.id)
    return paper
