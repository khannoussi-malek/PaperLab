import uuid
from typing import Annotated

from fastapi import APIRouter, Form, Header, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import DiscoveryDep, SessionDep
from app.config import settings
from app.core import discovery, enrichment, paper_events, papers, tags, workspaces
from app.core.errors import Conflict, InvalidInput
from app.core.note_counts import MAX_PAPERS, note_counts
from app.core.pipeline import MAX_UPLOAD_PDF_BYTES
from app.core.queue import INGEST_QUEUE
from app.models import PaperStatus
from app.schemas.discovery import CandidateOut
from app.schemas.papers import (
    ChunkOut,
    FoundPdfOut,
    FoundPdfsSeen,
    NoteCountsIn,
    NoteCountsOut,
    PaperEventOut,
    PaperOut,
    PaperUpdate,
    ReadingIn,
)
from app.schemas.tags import PaperTagGroup

router = APIRouter(prefix="/api/papers", tags=["papers"])


async def _enqueue_ingest(request: Request, paper_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("ingest_paper", str(paper_id), _queue_name=INGEST_QUEUE)


@router.post("", status_code=201)
async def upload_paper(
    file: UploadFile,
    request: Request,
    session: SessionDep,
    workspace_id: Annotated[uuid.UUID | None, Form()] = None,
) -> PaperOut:
    """workspace_id: also add the new paper to this workspace (404 before anything is stored if it's unknown)."""
    if workspace_id is not None:
        await workspaces.get(session, workspace_id)
    paper = await papers.create_paper(session, file.filename or "untitled.pdf", await file.read(), settings.pdf_dir)
    if workspace_id is not None:
        await workspaces.add_paper(session, workspace_id, paper.id)
    await _enqueue_ingest(request, paper.id)
    return paper


@router.get("")
async def list_papers(session: SessionDep) -> list[PaperOut]:
    return await papers.list_papers(session)


# Before the /{paper_id} routes, or "found-pdfs" is parsed as an id.
@router.get("/found-pdfs")
async def list_found_pdfs(session: SessionDep) -> list[FoundPdfOut]:
    """The free copies the weekly re-check found that the owner hasn't dismissed, newest first."""
    return [
        FoundPdfOut(id=event.id, paper_id=event.paper_id, title=title, created_at=event.created_at)
        for event, title in await paper_events.unseen_found(session)
    ]


@router.post("/found-pdfs/seen", status_code=204)
async def mark_found_pdfs_seen(payload: FoundPdfsSeen, session: SessionDep) -> None:
    await paper_events.mark_seen(session, payload.ids)


@router.post("/note-counts")
async def paper_note_counts(payload: NoteCountsIn, session: SessionDep) -> NoteCountsOut:
    if len(payload.paper_ids) > MAX_PAPERS:
        raise InvalidInput("too_many_papers", max=MAX_PAPERS)
    return NoteCountsOut(counts=await note_counts(session, payload.paper_ids))


@router.get("/{paper_id}")
async def get_paper(paper_id: uuid.UUID, session: SessionDep) -> PaperOut:
    return await papers.get_paper(session, paper_id)


@router.patch("/{paper_id}")
async def correct_paper(paper_id: uuid.UUID, payload: PaperUpdate, request: Request, session: SessionDep) -> PaperOut:
    fields = payload.model_dump(exclude_unset=True)
    paper = await enrichment.correct_metadata(session, paper_id, fields)
    rebuilt = not {"title", "abstract"}.isdisjoint(fields) and not paper.has_pdf  # its abstract chunk was rebuilt
    if rebuilt and paper.status == PaperStatus.EMBEDDING:
        paper_id = paper.id
        try:
            await request.app.state.arq.enqueue_job("index_abstract", str(paper_id), _queue_name=INGEST_QUEUE)
        except Exception:
            await papers.set_status(session, paper_id, PaperStatus.READY)  # never left at embedding with no job
            raise
    return paper


@router.put("/{paper_id}/reading")
async def set_reading(
    paper_id: uuid.UUID,
    payload: ReadingIn,
    session: SessionDep,
    x_paperlab_source: Annotated[str, Header()] = "reader",
) -> PaperOut:
    """The reader's passes finished and decision (D119). Only the fields sent change. 404 unknown paper; 422 for an
    empty body, a level outside 0–3, a null level, an unknown decision or any other field. The optional
    X-PaperLab-Source header (reader, library) says where the change came from; any other value is 422."""
    return await papers.set_reading(session, paper_id, payload.model_dump(exclude_unset=True), source=x_paperlab_source)


@router.delete("/{paper_id}", status_code=204)
async def delete_paper(paper_id: uuid.UUID, session: SessionDep) -> Response:
    await papers.delete_paper(session, paper_id)
    return Response(status_code=204)


@router.get("/{paper_id}/file", response_class=FileResponse)
async def get_paper_file(paper_id: uuid.UUID, session: SessionDep) -> FileResponse:
    return FileResponse(await papers.get_paper_file(session, paper_id), media_type="application/pdf")


@router.get("/{paper_id}/similar")
async def similar_papers(paper_id: uuid.UUID, session: SessionDep, providers: DiscoveryDep) -> list[CandidateOut]:
    """Papers like this one, from Semantic Scholar. 409 when it's off in Settings, doesn't know the paper or is busy."""
    return await discovery.similar(session, providers, await papers.get_paper(session, paper_id))


@router.get("/{paper_id}/events")
async def list_paper_events(paper_id: uuid.UUID, session: SessionDep) -> list[PaperEventOut]:
    """What happened to the paper, newest first. 404 unknown paper."""
    await papers.get_paper(session, paper_id)
    return await paper_events.history(session, paper_id)


@router.get("/{paper_id}/chunks")
async def list_chunks(paper_id: uuid.UUID, session: SessionDep, page: int | None = None) -> list[ChunkOut]:
    return await papers.list_chunks(session, paper_id, page)


@router.post("/{paper_id}/reingest", status_code=202)
async def reingest_paper(paper_id: uuid.UUID, request: Request, session: SessionDep) -> PaperOut:
    paper = await papers.get_paper(session, paper_id)
    if paper.file_path is None:
        raise Conflict("no_pdf", detail="This paper has no PDF yet.")
    # Flips the status before enqueueing, so a chat request racing the worker sees `uploaded`
    # (paper_not_ready) instead of a `ready` paper whose chunks are mid-replacement.
    await papers.set_status(session, paper.id, PaperStatus.UPLOADED)
    await session.refresh(paper)
    await _enqueue_ingest(request, paper.id)
    return paper


@router.post("/{paper_id}/pdf")
async def upload_paper_pdf(paper_id: uuid.UUID, file: UploadFile, request: Request, session: SessionDep) -> PaperOut:
    """The PDF of a paper saved without one: the same paper upgrades in place, keeping its tags, notes, workspaces and
    decisions, and its hits awaiting the PDF count as retrieved (manual). Ingest is queued. 404 unknown paper; 409
    already_has_pdf; 422 not_a_pdf or pdf_too_large."""
    if (await papers.get_paper(session, paper_id)).has_pdf:  # refused unread; attach_pdf re-checks under its lock
        raise Conflict("already_has_pdf")
    too_large = InvalidInput("pdf_too_large", max_mb=MAX_UPLOAD_PDF_BYTES // 1024 // 1024)
    if (file.size or 0) > MAX_UPLOAD_PDF_BYTES:  # refused unread when the size is known
        raise too_large
    if len(data := await file.read()) > MAX_UPLOAD_PDF_BYTES:
        raise too_large
    paper = await papers.attach_pdf(session, paper_id, data, how="manual")
    await _enqueue_ingest(request, paper.id)
    return paper


@router.post("/{paper_id}/find-pdf")
async def find_paper_pdf(
    paper_id: uuid.UUID, request: Request, session: SessionDep, providers: DiscoveryDep
) -> PaperOut:
    """Looks for a free copy of a paper saved without a PDF, as Find papers' Add does, and upgrades it in place when
    one is found (its awaiting hits count as imported); ingest is queued. 404 unknown paper; 409 already_has_pdf,
    already_in_library with paper_id (its arXiv copy is held), or no_free_pdf with tried and free_copies."""
    paper = await papers.get_paper(session, paper_id)
    if paper.has_pdf:
        raise Conflict("already_has_pdf")
    try:
        data, tried, copies = await discovery.find_pdf(session, providers, discovery.candidate_of(paper))
    except Conflict as exc:
        if str(exc) != discovery.ALREADY_IN_LIBRARY:
            raise
        raise Conflict("already_in_library", **exc.details) from exc
    if data is None:  # a check like the weekly re-check's: it waits a week before repeating this lookup
        await papers.record_no_free_pdf(session, paper_id)
        raise Conflict("no_free_pdf", tried=tried, free_copies=copies)
    paper = await papers.attach_pdf(session, paper_id, data, how="imported")
    await _enqueue_ingest(request, paper.id)
    return paper


@router.get("/{paper_id}/tags")
async def paper_tags(paper_id: uuid.UUID, session: SessionDep) -> list[PaperTagGroup]:
    await papers.get_paper(session, paper_id)
    return [
        PaperTagGroup(workspace_id=w, workspace_name=n, tags=t)
        for w, n, t in await tags.tags_of_paper(session, paper_id)
    ]
