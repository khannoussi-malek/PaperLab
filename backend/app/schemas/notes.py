import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.notes import DEFAULT_COLOR
from app.schemas.papers import Rect

# #rrggbb in either case; the notes service stores it lowercased.
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


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


class ChartRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str


class NoteCreate(BaseModel):
    body: str = Field(default="", max_length=50_000)
    color: HexColor = DEFAULT_COLOR
    anchor: AnchorIn


class NoteUpdate(BaseModel):
    body: str | None = Field(default=None, max_length=50_000)
    color: HexColor | None = None

    @model_validator(mode="after")
    def has_a_change(self) -> Self:
        if self.body is None and self.color is None:
            raise ValueError("send a body, a color, or both")
        return self


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    provenance: Literal["human", "llm", "llm_edited"]
    color: str
    source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    anchors: list[AnchorOut]
    charts: list[ChartRefOut]  # charts shown in the note, by title
