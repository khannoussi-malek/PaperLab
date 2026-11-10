import uuid
from typing import Literal

from pydantic import BaseModel, Field


class NoveltyIn(BaseModel):
    text: str = Field(max_length=100_000)  # transport cap only; text_too_long (6000) is the user-facing refusal
    workspace: str | None = None


class NoveltyPaperOut(BaseModel, from_attributes=True):
    paper_id: uuid.UUID
    title: str
    year: int | None
    label: Literal["very close", "related", "distant"]
    distance: float
    passage: str
    page: int | None
    section: str | None
    from_abstract: bool
    chunk_id: uuid.UUID


class NoveltyOut(BaseModel, from_attributes=True):
    papers: list[NoveltyPaperOut]
    searched_papers: int
    note: str
