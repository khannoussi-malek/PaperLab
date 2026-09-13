import uuid

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.core import notes
from app.schemas.chat import PromoteRequest
from app.schemas.notes import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(tags=["notes"])


@router.get("/api/papers/{paper_id}/notes")
async def list_paper_notes(paper_id: uuid.UUID, session: SessionDep) -> list[NoteOut]:
    return await notes.list_notes_for_paper(session, paper_id)


@router.post("/api/notes", status_code=201)
async def create_note(payload: NoteCreate, session: SessionDep) -> NoteOut:
    anchor = notes.Anchor(**payload.anchor.model_dump())
    return await notes.create_human_note(session, payload.body, anchor, payload.color)


@router.post("/api/notes/promote", status_code=201)
async def promote_note(payload: PromoteRequest, session: SessionDep) -> NoteOut:
    return await notes.promote_llm_fragment(session, payload.output_id, payload.body, payload.chunk_ids)


@router.patch("/api/notes/{note_id}")
async def update_note(note_id: uuid.UUID, payload: NoteUpdate, session: SessionDep) -> NoteOut:
    return await notes.update_note(session, note_id, body=payload.body, color=payload.color)


@router.delete("/api/notes/{note_id}", status_code=204)
async def delete_note(note_id: uuid.UUID, session: SessionDep) -> Response:
    await notes.delete_note(session, note_id)
    return Response(status_code=204)
