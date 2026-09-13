import uuid

from fastapi import APIRouter, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import SessionDep
from app.config import settings
from app.core import papers
from app.schemas.papers import ChunkOut, PaperOut

router = APIRouter(prefix="/api/papers", tags=["papers"])


async def _enqueue_ingest(request: Request, paper_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("ingest_paper", str(paper_id))


@router.post("", status_code=201)
async def upload_paper(file: UploadFile, request: Request, session: SessionDep) -> PaperOut:
    paper = await papers.create_paper(session, file.filename or "untitled.pdf", await file.read(), settings.pdf_dir)
    await _enqueue_ingest(request, paper.id)
    return paper


@router.get("")
async def list_papers(session: SessionDep) -> list[PaperOut]:
    return await papers.list_papers(session)


@router.get("/{paper_id}")
async def get_paper(paper_id: uuid.UUID, session: SessionDep) -> PaperOut:
    return await papers.get_paper(session, paper_id)


@router.delete("/{paper_id}", status_code=204)
async def delete_paper(paper_id: uuid.UUID, session: SessionDep) -> Response:
    await papers.delete_paper(session, paper_id)
    return Response(status_code=204)


@router.get("/{paper_id}/file", response_class=FileResponse)
async def get_paper_file(paper_id: uuid.UUID, session: SessionDep) -> FileResponse:
    return FileResponse(await papers.get_paper_file(session, paper_id), media_type="application/pdf")


@router.get("/{paper_id}/chunks")
async def list_chunks(paper_id: uuid.UUID, session: SessionDep, page: int | None = None) -> list[ChunkOut]:
    return await papers.list_chunks(session, paper_id, page)


@router.post("/{paper_id}/reingest", status_code=202)
async def reingest_paper(paper_id: uuid.UUID, request: Request, session: SessionDep) -> PaperOut:
    paper = await papers.get_paper(session, paper_id)
    await _enqueue_ingest(request, paper.id)
    return paper
