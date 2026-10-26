import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import APIRouter, Form, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import SessionDep
from app.core import manuscript_bib, manuscript_history, manuscript_templates, manuscript_zip, manuscripts
from app.core import manuscript_paths as paths
from app.core.errors import Conflict, InvalidInput, NotFound
from app.schemas.manuscripts import (
    CompileOut,
    FileOut,
    FilePut,
    FileTextOut,
    ManuscriptCreate,
    ManuscriptDetailOut,
    ManuscriptImportOut,
    ManuscriptOut,
    ManuscriptPatch,
    RenameIn,
    SnapshotOut,
    TemplateOut,
)

router = APIRouter(tags=["manuscripts"])
CHUNK = 1024**2


async def _detail(session: SessionDep, manuscript) -> ManuscriptDetailOut:
    files = await manuscripts.files(session, manuscript.id)
    return ManuscriptDetailOut.model_validate({**ManuscriptOut.model_validate(manuscript).model_dump(), "files": files})


async def _read_capped(file: UploadFile, cap: int, code: str = "file_too_large") -> bytes:
    """The upload's bytes, refusing as soon as they pass `cap`: a Content-Length that lies changes nothing."""
    data = bytearray()
    while chunk := await file.read(CHUNK):
        data += chunk
        if len(data) > cap:
            raise Conflict(code, limit=cap)
    return bytes(data)


@router.get("/api/templates/manuscripts")
async def list_templates() -> list[TemplateOut]:
    return [TemplateOut(name=name, label=label) for name, label in manuscript_templates.TEMPLATES.items()]


@router.get("/api/workspaces/{workspace_id}/manuscripts")
async def list_workspace_manuscripts(workspace_id: uuid.UUID, session: SessionDep) -> list[ManuscriptOut]:
    return await manuscripts.list_for(session, workspace_id=workspace_id)


@router.get("/api/manuscripts")
async def list_orphan_manuscripts(orphans: bool, session: SessionDep) -> list[ManuscriptOut]:
    """Manuscripts with no workspace (`orphans=true`; the only listing here)."""
    if not orphans:
        raise InvalidInput("orphans_only")
    return await manuscripts.list_for(session, workspace_id=None)


@router.post("/api/manuscripts", status_code=201)
async def create_manuscript(payload: ManuscriptCreate, session: SessionDep) -> ManuscriptDetailOut:
    created = await manuscripts.create(session, title=payload.title, template=payload.template,
                                       workspace_id=payload.workspace_id)
    await session.commit()
    return await _detail(session, created)


@router.post("/api/manuscripts/import", status_code=201)
async def import_manuscript(file: UploadFile, session: SessionDep,
                            workspace_id: uuid.UUID | None = Form(default=None)) -> ManuscriptImportOut:
    """An Overleaf zip as a new manuscript, all or nothing."""
    files, main_file, skipped = manuscript_zip.read_zip(
        await _read_capped(file, paths.MAX_TOTAL, "manuscript_too_large"))
    title = PurePosixPath(file.filename or "").stem or "Imported manuscript"
    try:
        created = await manuscripts.create_from_files(session, title=title, workspace_id=workspace_id, files=files,
                                                      main_file=main_file)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return ManuscriptImportOut(**(await _detail(session, created)).model_dump(), skipped=skipped)


@router.get("/api/manuscripts/{manuscript_id}")
async def get_manuscript(manuscript_id: uuid.UUID, session: SessionDep) -> ManuscriptDetailOut:
    return await _detail(session, await manuscripts.get(session, manuscript_id))


@router.patch("/api/manuscripts/{manuscript_id}")
async def patch_manuscript(
    manuscript_id: uuid.UUID, payload: ManuscriptPatch, session: SessionDep
) -> ManuscriptDetailOut:
    updated = await manuscripts.update(session, manuscript_id, **payload.model_dump(exclude_unset=True))
    await session.commit()
    return await _detail(session, updated)


@router.delete("/api/manuscripts/{manuscript_id}", status_code=204)
async def delete_manuscript(manuscript_id: uuid.UUID, session: SessionDep) -> Response:
    await manuscripts.delete(session, manuscript_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/api/manuscripts/{manuscript_id}/files/{path:path}", response_model=FileTextOut)
async def get_file(manuscript_id: uuid.UUID, path: str, session: SessionDep):
    """A text file as JSON, a binary as its bytes."""
    row = await manuscripts.read(session, manuscript_id, path)
    if row.text is not None:
        return FileTextOut(path=row.path, text=row.text, updated_at=row.updated_at)
    return Response(row.data, media_type=mimetypes.guess_type(path)[0] or "application/octet-stream")


@router.put("/api/manuscripts/{manuscript_id}/files/{path:path}")
async def put_file(manuscript_id: uuid.UUID, path: str, payload: FilePut, session: SessionDep) -> FileOut:
    """409 file_changed (with updated_at) when the file moved on since base_updated_at; 409 file_exists with no base."""
    saved = await manuscripts.save_text(session, manuscript_id, path, payload.text, base=payload.base_updated_at)
    await session.commit()
    return saved


@router.post("/api/manuscripts/{manuscript_id}/uploads", status_code=201)
async def upload_file(manuscript_id: uuid.UUID, file: UploadFile, session: SessionDep,
                      path: str = Form()) -> FileOut:
    """A binary (overwrites) or a new text file (409 file_exists when there is one)."""
    await manuscripts.get(session, manuscript_id)
    text = paths.is_text(paths.validate_path(path))
    data = await _read_capped(file, paths.MAX_TEXT if text else paths.MAX_BINARY)
    if not text:
        saved = await manuscripts.put_binary(session, manuscript_id, path, data)
    else:
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidInput("not_text", path=path) from exc
        saved = await manuscripts.save_text(session, manuscript_id, path, decoded, base=None)
    await session.commit()
    return saved


@router.post("/api/manuscripts/{manuscript_id}/files/{path:path}/rename")
async def rename_file(manuscript_id: uuid.UUID, path: str, payload: RenameIn, session: SessionDep) -> FileOut:
    renamed = await manuscripts.rename(session, manuscript_id, path, payload.new_path)
    await session.commit()
    return renamed


@router.delete("/api/manuscripts/{manuscript_id}/files/{path:path}", status_code=204)
async def delete_file(manuscript_id: uuid.UUID, path: str, session: SessionDep) -> Response:
    await manuscripts.remove(session, manuscript_id, path)
    await session.commit()
    return Response(status_code=204)


@router.post("/api/manuscripts/{manuscript_id}/compile", status_code=202)
async def compile_manuscript(manuscript_id: uuid.UUID, session: SessionDep) -> CompileOut:
    return CompileOut(state=await manuscripts.request_compile(session, manuscript_id, now=datetime.now(timezone.utc)))


@router.get("/api/manuscripts/{manuscript_id}/pdf", response_class=FileResponse)
async def get_pdf(manuscript_id: uuid.UUID, session: SessionDep) -> FileResponse:
    await manuscripts.get(session, manuscript_id)
    target = manuscripts.pdf_path(manuscript_id)
    if not target.is_file():
        raise NotFound("no_pdf")
    return FileResponse(target, media_type="application/pdf")


@router.get("/api/manuscripts/{manuscript_id}/snapshots")
async def list_snapshots(manuscript_id: uuid.UUID, session: SessionDep) -> list[SnapshotOut]:
    await manuscripts.get(session, manuscript_id)
    return await manuscript_history.list_(session, manuscript_id)


@router.post("/api/manuscripts/{manuscript_id}/snapshots/{snapshot_id}/restore", status_code=204)
async def restore_snapshot(manuscript_id: uuid.UUID, snapshot_id: uuid.UUID, session: SessionDep) -> Response:
    await manuscript_history.restore(session, manuscript_id, snapshot_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/api/manuscripts/{manuscript_id}/export.zip")
async def export_zip(manuscript_id: uuid.UUID, session: SessionDep) -> Response:
    manuscript = await manuscripts.get(session, manuscript_id)
    listed = await manuscripts.files(session, manuscript_id)
    rows = [await manuscripts.read(session, manuscript_id, f.path) for f in listed]
    files = {r.path: r.text if r.text is not None else r.data for r in rows}
    bib = await manuscript_bib.build_bib(session, manuscript, {p: c for p, c in files.items() if isinstance(c, str)})
    await session.commit()  # the keys the bib pinned, as a compile pins them
    target = manuscripts.pdf_path(manuscript_id)
    data = manuscript_zip.write_zip(files, bib, target.read_bytes() if target.is_file() else None, manuscript.title)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="manuscript.zip"'})
