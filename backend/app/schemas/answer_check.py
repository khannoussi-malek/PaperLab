import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AnswerCheckRequest(BaseModel):
    model_id: uuid.UUID | None = None  # null: the default model
    confirm_remote: bool = False  # the reader said yes to sending the answer and its passages to a cloud model


class AnswerCheckSentenceOut(BaseModel):
    index: int
    text: str
    labels: list[str]
    state: Literal["pending", "done", "not_cited", "not_kept", "not_checked"]
    verdict: Literal["supported", "partially_supported", "not_supported", "not_addressed", "couldnt_check"] | None
    reason: str | None
    quote: str | None
    quote_label: str | None
    confidence: Literal["high", "low"] | None
    shortened: bool


class AnswerCheckOut(BaseModel):
    id: uuid.UUID
    state: Literal["running", "done", "failed"]
    model: str
    connection_name: str | None
    created_at: datetime
    summary: str
    limit_hit: bool
    sentences: list[AnswerCheckSentenceOut]
