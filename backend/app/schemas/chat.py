import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.papers import Rect


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


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
    paper_id: uuid.UUID  # the anchor the prompt quoted
    page: int
    provenance: Literal["human", "llm", "llm_edited"]


# SSE payloads, one model per event name: sources, token, done, error.
class SourcesEvent(BaseModel):
    whole_paper: bool  # the paper was small enough to send whole, so retrieval was skipped
    sources: list[ChatSource]
    notes: list[NoteSource]  # workspace chat only; [] for a paper
    notes_used: int | None  # notes that fit the prompt; null for a paper
    notes_total: int | None  # every note in the workspace; null for a paper


class TokenEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    output_id: uuid.UUID
    model: str
    prompt_version: int
    cited: list[str]  # C labels first-cited first, then N labels first-cited first


class ErrorEvent(BaseModel):
    message: str
    retryable: bool


class ChatAnswer(BaseModel):
    id: uuid.UUID
    question: str
    content: str
    model: str
    prompt_version: int
    created_at: datetime
    whole_paper: bool
    # sources[i] is C{i+1}. null: a re-ingest replaced that chunk, so its marker renders as plain text.
    sources: list[ChatSource | None]
    # notes[i] is N{i+1}. null: the note (or its paper) was deleted.
    notes: list[NoteSource | None]
    notes_used: int | None
    notes_total: int | None


class PromoteRequest(BaseModel):
    output_id: uuid.UUID
    body: str = Field(max_length=50_000)
    chunk_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
