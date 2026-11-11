import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["queued", "running", "done", "failed", "interrupted"]


class DraftReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["light", "full"] = "light"
    confirm_remote: bool = False
    confirm_full: bool = False  # full mode runs up to 54 calls: asked for twice, like confirm_large elsewhere


class IssueOut(BaseModel):
    id: str
    severity: Literal["blocker", "major", "minor", "nit"]
    section: str
    summary: str
    quote: str  # the author's own words, exactly as in the file: a reference, never replacement text
    close_criterion: str
    raised_by: list[str]
    file: str
    line: int


class RefutedOut(BaseModel):
    summary: str
    reason: str


class DraftReviewOut(BaseModel):
    id: uuid.UUID
    mode: Literal["light", "full"]
    status: Status
    stage: str | None
    calls_done: int
    calls_max: int
    reason: str | None
    issues: list[IssueOut]
    refuted: list[RefutedOut]
    counts: dict[str, int]
    model: str | None
    ai: Literal[True] = True
    created_at: datetime


class DraftReviewState(BaseModel):
    review: DraftReviewOut | None


class ModeEstimate(BaseModel):
    mode: Literal["light", "full"]
    likely_calls: int
    max_calls: int
    approx_input_tokens: int


class DraftReviewEstimate(BaseModel):
    paper_chars: int
    too_long: bool
    modes: list[ModeEstimate]
