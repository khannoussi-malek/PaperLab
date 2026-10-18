import uuid
from collections.abc import Callable
from typing import IO, Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.core import citations_import_run, pipeline
from app.core.citations_export import FORMATS, filename_slug
from app.schemas.citations_import import ImportPreviewOut, ImportProgressOut

router = APIRouter(tags=["citations"])

# The zip cap plus room for the form's other fields and the multipart framing.
IMPORT_BODY_MAX = citations_import_run.ZIP_MAX_BYTES + 1024 * 1024


class ExportIn(BaseModel):
    paper_ids: list[uuid.UUID]
    format: str  # one of FORMATS; anything else is 422 unknown_format


def download(text: str, fmt: str, name: str) -> Response:
    content_type, ext = FORMATS[fmt]
    headers = {"Content-Disposition": f'attachment; filename="{filename_slug(name)}.{ext}"'}
    return Response(text, media_type=f"{content_type}; charset=utf-8", headers=headers)


@router.post("/api/citations/export")
async def export_selection(payload: ExportIn, session: SessionDep) -> Response:
    """The selected papers, in the order given, as a download. 422 for an unknown format, none, or over 1000."""
    text, _ = await pipeline.export_citations(session, paper_ids=payload.paper_ids, fmt=payload.format)
    return download(text, payload.format, "citations")


# ---- import (M40 Task 9a) ----


class CappedBody(APIRoute):
    """413 for a body over IMPORT_BODY_MAX: a declared Content-Length before anything is read, else as the body
    streams in, so an oversize upload is never read whole."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def capped(request: Request) -> Response:
            too_big = citations_import_run.UPLOAD_TOO_BIG
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > IMPORT_BODY_MAX:
                return JSONResponse({"detail": too_big}, status_code=413)
            seen = 0

            async def receive():
                nonlocal seen
                message = await request.receive()
                seen += len(message.get("body", b""))
                if seen > IMPORT_BODY_MAX:
                    raise HTTPException(413, too_big)
                return message

            return await handler(Request(request.scope, receive))

        return capped


imports = APIRouter(tags=["citations"], route_class=CappedBody)


def _upload(file: UploadFile) -> tuple[str, IO[bytes]]:
    """The upload's name and its spooled file, read from there (a zip never whole): 413 over its kind's cap (20 MB a
    file, 200 MB a zip)."""
    name = file.filename or citations_import_run.RAW_TEXT_NAME
    if (file.size or 0) > citations_import_run.cap(name):
        raise HTTPException(413, citations_import_run.too_big(name))
    return name, file.file


@imports.post("/api/citations/import/preview")
async def preview_import(
    file: UploadFile,
    session: SessionDep,
    workspace_id: Annotated[uuid.UUID | None, Form()] = None,
    fetch_free_pdfs: Annotated[bool, Form()] = True,
) -> ImportPreviewOut:
    """What importing the file (a references file or a Zotero zip) would do: counts, and `disclosure`, the sentence
    to show when free-copy sources will be contacted. Nothing is written and no paper source is contacted. 422 for
    an unreadable file, 413 over the size caps."""
    name, source = _upload(file)
    return await citations_import_run.preview(
        session, name, source, workspace_id=workspace_id, fetch_free_pdfs=fetch_free_pdfs
    )


@imports.post("/api/citations/import", responses={202: {"model": ImportProgressOut}})
async def import_citations(
    file: UploadFile,
    session: SessionDep,
    response: Response,
    workspace_id: Annotated[uuid.UUID | None, Form()] = None,
    new_workspace_name: Annotated[str | None, Form()] = None,
    fetch_free_pdfs: Annotated[bool, Form()] = True,
) -> ImportProgressOut:
    """Imports a references file or a Zotero zip into the library, and into `workspace_id` or a new workspace
    named `new_workspace_name` (made only once the file has parsed). 200 with the result (state finished) when it
    ran now; 202 with `job_id` (state queued) to poll at GET /api/citations/import/{job_id}. 422 for an unreadable
    file or both targets, 404 unknown workspace, 409 a taken name, 413 over the size caps."""
    name, source = _upload(file)
    progress = await citations_import_run.start(
        session, name, source, workspace_id=workspace_id, new_workspace_name=new_workspace_name,
        fetch_free_pdfs=fetch_free_pdfs,
    )  # fmt: skip
    if progress.state == "queued":
        response.status_code = 202
    return progress


router.include_router(imports)


@router.get("/api/citations/import/{job_id}")
async def import_progress(job_id: str, request: Request) -> ImportProgressOut:
    """An import job's state: queued, running (with counts), finished (with the result), failed, restarted (PaperLab
    restarted before it finished) or expired (unknown or over a day old), the last three with a message in words."""
    return await citations_import_run.status(request.app.state.arq, job_id)
