import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.chat import ChatSource


class CheckRequest(BaseModel):
    model_id: uuid.UUID | None = None  # null: the default model
    confirm_remote: bool = False  # the reader said yes to sending the note and passages to a cloud model


class CheckLineOut(BaseModel):
    verdict: Literal["missing", "unsupported", "supported"]
    text: str  # as kept; the model's own reply never leaves the server (D118)


class CheckOut(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    lines: list[CheckLineOut]
    dropped: int  # lines of the reply that broke the check's rules and were left out
    sources: list[ChatSource | None]  # sources[i] is C{i+1}; null: a re-ingest replaced that chunk
    whole_paper: bool
    model: str
    connection_name: str | None
    prompt_version: int
    created_at: datetime
    stale: bool  # the note changed after the check
