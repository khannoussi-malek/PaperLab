import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.papers import Rect


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    model_id: uuid.UUID | None = None  # a model from GET /api/llm/models; None asks the default
    parent_id: uuid.UUID | None = None  # the answer this question follows up; paper chat only


class ChatSource(BaseModel):
    label: str  # "C1": the marker the answer cites
    chunk_id: uuid.UUID
    paper_id: uuid.UUID  # workspace chat cites several papers
    page: int
    section: str | None
    bbox: list[Rect]


class NoteSource(BaseModel):
    label: str  # "N1": the marker the answer cites
    note_id: uuid.UUID
    paper_id: uuid.UUID  # the paper the prompt named it by
    page: int | None  # null: the note is on the whole paper
    provenance: Literal["human", "llm", "llm_edited"]


# SSE payloads, one model per event name: sources, token, done, error.
class SourcesEvent(BaseModel):
    whole_paper: bool  # the paper was small enough to send whole, so retrieval was skipped
    sources: list[ChatSource]
    notes: list[NoteSource]
    notes_used: int | None  # notes that fit the prompt
    notes_total: int | None  # every note in the paper or workspace


class TokenEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    output_id: uuid.UUID
    model: str
    connection_name: str
    prompt_version: int
    cited: list[str]  # C labels first-cited first, then N labels first-cited first


class ErrorEvent(BaseModel):
    message: str
    retryable: bool


class SavedNoteOut(BaseModel):
    index: int  # the answer's :::note block it was saved from, from 0
    note_id: uuid.UUID
    paper_ids: list[uuid.UUID]  # the note's papers now, by title: where the card's Open goes


class ChatAnswer(BaseModel):
    id: uuid.UUID
    question: str
    content: str
    model: str
    connection_name: str | None  # null for answers written before model connections existed
    prompt_version: int
    created_at: datetime
    whole_paper: bool
    # sources[i] is C{i+1}. null: a re-ingest replaced that chunk, so its marker renders as plain text.
    sources: list[ChatSource | None]
    # notes[i] is N{i+1}. null: the note was deleted, or is no longer linked to a paper in scope.
    notes: list[NoteSource | None]
    notes_used: int | None
    notes_total: int | None
    parent_id: uuid.UUID | None  # the answer this one follows up; null for a question asked on its own
    saved_notes: list[SavedNoteOut]  # its suggested notes already saved, by block


class PromoteRequest(BaseModel):
    output_id: uuid.UUID
    body: str = Field(max_length=50_000)
    chunk_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SaveSuggestion(BaseModel):
    index: int = Field(ge=0)  # the answer's :::note block, from 0
