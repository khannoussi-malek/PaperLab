import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.papers import PaperOut

CARD_MS_CAP = 1_800_000  # half an hour: a card left open overnight is not reading time


class TriageDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pile: Literal["read_closely", "skim", "later", "not_relevant", "skip"]
    session_id: uuid.UUID
    client_id: uuid.UUID | None = None
    reason: str | None = None
    note: str | None = None  # plain str: the 500 limit is core's note_too_long 422
    fivecs: int | None = Field(default=None, ge=0, le=31)
    pdf_opened: bool = False
    pdf_ms: int | None = Field(default=None, ge=0)
    card_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _cap_card_ms(self):
        if self.card_ms is not None:
            self.card_ms = min(self.card_ms, CARD_MS_CAP)
        return self


class TriageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paper_id: uuid.UUID
    session_id: uuid.UUID | None
    client_id: uuid.UUID | None
    source: str
    pile: str | None
    before_triage: str | None
    after_triage: str | None
    before_pass: int
    after_pass: int
    reason: str | None
    note: str | None
    fivecs: int | None
    pdf_opened: bool
    pdf_ms: int | None
    card_ms: int | None
    undone_event_id: uuid.UUID | None
    created_at: datetime


class TriageDecisionOut(BaseModel):
    paper: PaperOut
    event: TriageEventOut


class TriageReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    note: str | None = None
