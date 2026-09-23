import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SearchRunCreate(BaseModel):
    query: str
    filters: dict = {}
    sources: list[str]
    query_overrides: dict = {}


class SearchRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    query_text: str
    filters_json: dict
    sources_json: list[str]
    status: str
    started_at: datetime
    stopped_at: datetime | None
    stats_json: dict


class HitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    external_ref_id: uuid.UUID | None
    source_method: str
    normalized_title: str
    first_seen_at: datetime
    stage1_status: str | None
    stage1_exclude_reason: str | None
    stage1_note: str | None
    priority: int | None
    topic_fit: str | None
    acquisition_status: str
    paper_id: uuid.UUID | None


class HitListOut(BaseModel):
    items: list[HitOut]
    next_cursor: str | None
