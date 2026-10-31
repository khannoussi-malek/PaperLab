import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.sections import Role

Status = Literal["queued", "running", "done", "failed", "interrupted"]


class SectionReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    base: AwareDatetime  # the file's updated_at the editor last saw
    at: int = Field(ge=0, description="UTF-16 code units, as in JavaScript strings")
    role: str | None = None  # None: use the guess from the heading
    confirm_remote: bool = False


class RefOut(BaseModel):
    kind: Literal["sentence", "note"]
    n: int
    hash: str | None = None
    preview: str | None = None
    note_id: uuid.UUID | None = None
    paper_id: uuid.UUID | None = None
    label: str | None = None


class FindingOut(BaseModel):
    kind: Literal["missing", "unsupported", "supported"]
    point: str
    refs: list[RefOut]


class SectionReviewOut(BaseModel):
    id: uuid.UUID
    file: str
    section_hash: str
    title: str
    role: Role
    role_source: Literal["guessed", "chosen"]
    status: Status
    reason: str | None
    findings: list[FindingOut]
    dropped: int
    model: str | None
    ai: Literal[True] = True
    created_at: datetime


class SectionReviewsOut(BaseModel):
    reviews: list[SectionReviewOut]


class SectionLocateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    text: str = Field(max_length=3_000_000)  # the core names the real cap


class SectionSpanOut(BaseModel):
    title: str
    start: int = Field(description="UTF-16 code units, as in JavaScript strings")
    end: int = Field(description="UTF-16 code units, as in JavaScript strings")
    hash: str
    words: int
    guess: Role | None


class SectionLocateOut(BaseModel):
    sections: list[SectionSpanOut]
