import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.papers import Rect


class AnchorIn(BaseModel):
    paper_id: uuid.UUID
    page: int = Field(ge=1)
    bbox: list[Rect] = Field(min_length=1, max_length=500)
    quoted_text: str = Field(min_length=1, max_length=20_000)


class AnchorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paper_id: uuid.UUID
    page: int
    bbox: list[Rect]
    quoted_text: str


class NoteCreate(BaseModel):
    body: str = Field(default="", max_length=50_000)
    anchor: AnchorIn


class NoteUpdate(BaseModel):
    body: str = Field(max_length=50_000)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    provenance: Literal["human", "llm", "llm_edited"]
    source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    anchors: list[AnchorOut]
