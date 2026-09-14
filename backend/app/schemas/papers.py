import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# PDF points, top-left origin: (x0, y0, x1, y1). A tuple so OpenAPI (and the TS types) say 4 numbers.
Rect = tuple[float, float, float, float]


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doi: str | None
    openalex_id: str | None
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    venue: str | None
    type: str | None
    is_retracted: bool
    oa_status: str | None
    oa_url: str | None
    cited_by_count: int | None
    referenced_works_count: int | None
    issn: str | None
    page_count: int | None
    status: str
    status_error: str | None
    created_at: datetime


AuthorName = Annotated[str, Field(min_length=1, max_length=300)]


class PaperUpdate(BaseModel):
    """A manual correction. Only the fields sent change; null clears venue, doi, abstract or year."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=1000)
    authors: list[AuthorName] | None = Field(default=None, max_length=500)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = Field(default=None, max_length=1000)
    doi: str | None = Field(default=None, max_length=300)
    # OpenAlex sometimes returns a wrong abstract (BERT's was its citation string); the user can fix or clear it.
    abstract: str | None = Field(default=None, max_length=10_000)
    is_retracted: bool | None = None

    @model_validator(mode="after")
    def is_a_correction(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one field to correct")
        required = {"authors", "is_retracted", "title"} & self.model_fields_set
        nulled = sorted(field for field in required if getattr(self, field) is None)
        if nulled:
            raise ValueError(f"{', '.join(nulled)} can't be null")
        return self


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    page: int
    bbox: list[Rect]
    section_title: str | None
    text: str
    strategy_ver: int
