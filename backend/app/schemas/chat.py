import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.papers import Rect


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatSource(BaseModel):
    label: str  # "C1": the marker the answer cites
    chunk_id: uuid.UUID
    page: int
    section: str | None
    bbox: list[Rect]


# SSE payloads, one model per event name: sources, token, done, error.
class SourcesEvent(BaseModel):
    whole_paper: bool  # the paper was small enough to send whole, so retrieval was skipped
    sources: list[ChatSource]


class TokenEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    output_id: uuid.UUID
    model: str
    prompt_version: int
    cited: list[str]  # labels, first-cited first


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


class PromoteRequest(BaseModel):
    output_id: uuid.UUID
    body: str = Field(max_length=50_000)
    chunk_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
