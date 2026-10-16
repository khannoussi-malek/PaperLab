import uuid
from dataclasses import asdict

from fastapi import APIRouter, Request, Response

from app.api.citations import download
from app.api.deps import SessionDep
from app.core import notes_markdown, pipeline, tags, workspace_search, workspaces
from app.core.citations_export import filename_slug
from app.schemas.notes import NoteOut
from app.schemas.papers import PaperOut
from app.schemas.tags import TagApply, TagDeleted, TagOut, TagRename, TagRenamed, TagResultOut
from app.schemas.workspace_search import EligibilityOut, EligibilityUpdate
from app.schemas.workspaces import WorkspaceCreate, WorkspaceOut, WorkspaceRename

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("")
async def list_workspaces(session: SessionDep) -> list[WorkspaceOut]:
    return await workspaces.list_workspaces(session)


@router.post("", status_code=201)
async def create_workspace(payload: WorkspaceCreate, session: SessionDep) -> WorkspaceOut:
    return await workspaces.create(session, payload.name)


@router.patch("/{workspace_id}")
async def rename_workspace(workspace_id: uuid.UUID, payload: WorkspaceRename, session: SessionDep) -> WorkspaceOut:
    return await workspaces.rename(session, workspace_id, payload.name)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: uuid.UUID, session: SessionDep) -> Response:
    await workspaces.delete(session, workspace_id)
    return Response(status_code=204)


@router.put("/{workspace_id}/papers/{paper_id}", status_code=204)
async def add_paper(workspace_id: uuid.UUID, paper_id: uuid.UUID, session: SessionDep) -> Response:
    await workspaces.add_paper(session, workspace_id, paper_id)
    return Response(status_code=204)


@router.delete("/{workspace_id}/papers/{paper_id}", status_code=204)
async def remove_paper(workspace_id: uuid.UUID, paper_id: uuid.UUID, session: SessionDep) -> Response:
    await workspaces.remove_paper(session, workspace_id, paper_id)
    return Response(status_code=204)


@router.get("/{workspace_id}/papers")
async def list_papers(workspace_id: uuid.UUID, session: SessionDep) -> list[PaperOut]:
    return await workspaces.papers(session, workspace_id)


@router.get("/{workspace_id}/notes")
async def list_notes(workspace_id: uuid.UUID, session: SessionDep) -> list[NoteOut]:
    return await workspaces.notes(session, workspace_id)


@router.patch("/{workspace_id}/papers/{paper_id}/eligibility")
async def set_eligibility(
    workspace_id: uuid.UUID, paper_id: uuid.UUID, run: uuid.UUID, payload: EligibilityUpdate, session: SessionDep,
) -> EligibilityOut:
    return await workspace_search.set_eligibility(
        session, workspace_id, paper_id, run, payload.status, payload.exclude_reason
    )


@router.get("/{workspace_id}/citations")
async def export_citations(workspace_id: uuid.UUID, format: str, session: SessionDep) -> Response:
    """The workspace's papers as a download: bibtex, ris, csljson, apa or apa-html. 404 unknown workspace, 422 for an
    unknown format or no papers."""
    text, _ = await pipeline.export_citations(session, workspace_id=workspace_id, fmt=format)
    return download(text, format, (await workspaces.get(session, workspace_id)).name)


@router.get("/{workspace_id}/notes.zip")
async def export_notes(workspace_id: uuid.UUID, request: Request, session: SessionDep) -> Response:
    """The workspace's notes as markdown files, one per paper, zipped for Obsidian. 404 unknown workspace."""
    origin = str(request.base_url).rstrip("/")
    data = await notes_markdown.export_workspace(session, workspace_id, origin)
    slug = filename_slug((await workspaces.get(session, workspace_id)).name)
    return Response(
        data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{slug}-notes.zip"'}
    )


@router.get("/{workspace_id}/tags")
async def list_tags(workspace_id: uuid.UUID, session: SessionDep) -> list[TagOut]:
    await workspaces.get(session, workspace_id)
    return [TagOut(**asdict(s)) for s in await tags.summaries(session, workspace_id)]


@router.get("/{workspace_id}/paper-tags")
async def paper_tags(workspace_id: uuid.UUID, session: SessionDep) -> dict[str, list[str]]:
    await workspaces.get(session, workspace_id)
    return {str(k): v for k, v in (await tags.paper_tag_map(session, workspace_id)).items()}


@router.post("/{workspace_id}/tags/apply")
async def apply_tag(workspace_id: uuid.UUID, payload: TagApply, session: SessionDep) -> TagResultOut:
    await workspaces.get(session, workspace_id)
    return TagResultOut(**asdict(await tags.tag_papers(session, workspace_id, payload.tag, payload.paper_ids)))


@router.post("/{workspace_id}/tags/remove")
async def remove_tag(workspace_id: uuid.UUID, payload: TagApply, session: SessionDep) -> TagResultOut:
    await workspaces.get(session, workspace_id)
    return TagResultOut(**asdict(await tags.untag_papers(session, workspace_id, payload.tag, payload.paper_ids)))


@router.patch("/{workspace_id}/tags/{tag_id}")
async def rename_tag(workspace_id: uuid.UUID, tag_id: uuid.UUID, payload: TagRename, session: SessionDep) -> TagRenamed:
    old, new = await tags.rename_by_id(session, workspace_id, tag_id, payload.new_name)
    return TagRenamed(old=old, new=new)


@router.delete("/{workspace_id}/tags/{tag_id}")
async def delete_tag(workspace_id: uuid.UUID, tag_id: uuid.UUID, session: SessionDep) -> TagDeleted:
    name, count = await tags.delete_by_id(session, workspace_id, tag_id)
    return TagDeleted(tag=name, papers=count)
