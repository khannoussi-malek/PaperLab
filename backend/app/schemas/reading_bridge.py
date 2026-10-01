import uuid

from pydantic import BaseModel


class ReadingContextOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    priority: int | None
    note: str | None
    stage2_status: str | None


class ReadingContextListOut(BaseModel):
    contexts: list[ReadingContextOut]


class ReadingQueueRowOut(BaseModel):
    paper_id: uuid.UUID
    title: str
    priority: int | None
    reading_pass: int
    triage: str | None
    note_count: int


class ReadingQueueOut(BaseModel):
    rows: list[ReadingQueueRowOut]
