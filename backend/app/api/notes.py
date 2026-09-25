import uuid
from typing import Literal

from fastapi import APIRouter, Response

from app.api.deps import LLMByModelIdDep, SessionDep
from app.core import note_suggestions, notes
from app.schemas.chat import PromoteRequest
from app.schemas.note_suggestions import NoteSuggestionOut, NoteSuggestionsOut
from app.schemas.notes import NoteCreate, NoteOut, NotePapersIn, NoteUpdate

router = APIRouter(tags=["notes"])


@router.get("/api/papers/{paper_id}/notes")
async def list_paper_notes(paper_id: uuid.UUID, session: SessionDep) -> list[NoteOut]:
    return await notes.list_notes_for_paper(session, paper_id)


@router.get("/api/notes")
async def list_notes(session: SessionDep, paper: uuid.UUID | Literal["none"] | None = None) -> list[NoteOut]:
    """Every note, newest first. `paper=<id>`: the notes linked to that paper (404 when there is none); `paper=none`:
    the notes on no paper. Any other value is a 422."""
    if paper == "none":
        return await notes.list_notes(session, unlinked=True)
    return await notes.list_notes(session, paper)


@router.put("/api/notes/{note_id}/papers")
async def set_note_papers(note_id: uuid.UUID, payload: NotePapersIn, session: SessionDep) -> NoteOut:
    """Replaces the note's papers. 404 for the note or `unknown_paper`; 422 over 100 papers."""
    return await notes.set_papers(session, note_id, payload.paper_ids)


@router.post("/api/papers/{paper_id}/notes/suggest")
async def suggest_notes(paper_id: uuid.UUID, session: SessionDep, llm: LLMByModelIdDep) -> NoteSuggestionsOut:
    """One-click suggestions, not automatic notes (P1 of this feature): the caller shows each as a card the
    reader accepts or dismisses individually, via the unchanged POST /api/notes/promote and this response's
    own output_id."""
    suggested = await note_suggestions.suggest(session, paper_id, llm)
    output_id = await note_suggestions.save_suggestions(session, paper_id, suggested, llm.model, llm.connection_name)
    return NoteSuggestionsOut(
        output_id=output_id,
        suggestions=[
            NoteSuggestionOut(
                body=s.body,
                chunk_id=s.source.id,
                page=s.source.page,
                section=s.source.section,
                bbox=s.source.bbox,
            )
            for s in suggested.suggestions
        ],
    )


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
