import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "done", "failed", "cancelled", "interrupted"]


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    file: str
    base: AwareDatetime  # the file's updated_at the editor last saw
    from_: int | None = Field(None, alias="from", ge=0, description="UTF-16 code units, as in JavaScript strings")
    to: int | None = Field(None, ge=0, description="UTF-16 code units, as in JavaScript strings")
    include_uncited: bool = True


class ReviewRunOut(BaseModel):
    id: uuid.UUID
    file: str
    status: RunStatus
    total: int
    done: int
    reason: str | None
    include_uncited: bool
    uncited_skipped: int
    created_at: datetime


class CheckItemOut(BaseModel):
    id: uuid.UUID
    kind: Literal["cited", "uncited"]
    file: str
    sentence_hash: str
    sentence: str
    ord: int
    cite_key: str | None
    paper_id: uuid.UUID | None
    paper_title: str | None
    status: Literal["queued", "running", "done", "failed", "interrupted"]
    verdict: str | None
    reason: str | None
    quote: str | None
    page: int | None
    chunk_id: uuid.UUID | None
    output_id: uuid.UUID | None
    model: str | None
    ai: Literal[True] = True


class ReviewOut(BaseModel):
    run: ReviewRunOut | None
    items: list[CheckItemOut]
    dismissed: list[str]


class LocateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=3_000_000)  # the core names the real cap


class SentenceOut(BaseModel):
    start: int = Field(description="UTF-16 code units, as in JavaScript strings")
    end: int = Field(description="UTF-16 code units, as in JavaScript strings")
    hash: str
    keys: list[str]


class LocateOut(BaseModel):
    sentences: list[SentenceOut]
