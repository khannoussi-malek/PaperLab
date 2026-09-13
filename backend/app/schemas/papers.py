import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# PDF points, top-left origin: (x0, y0, x1, y1). A tuple so OpenAPI (and the TS types) say 4 numbers.
Rect = tuple[float, float, float, float]


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doi: str | None
    title: str
    abstract: str | None
    authors: list[Any]
    year: int | None
    venue: str | None
    page_count: int | None
    status: str
    status_error: str | None
    created_at: datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    page: int
    bbox: list[Rect]
    section_title: str | None
    text: str
    strategy_ver: int
