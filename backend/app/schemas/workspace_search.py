import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Mirrors the DB CHECK constraints on workspace_search_hits (migration 0013): Literal + Field bounds reject a
# garbage value with a clean 422 in the schema layer, before it can reach the DB as an IntegrityError/500.
Stage1Status = Literal["relevant", "not_relevant", "maybe"]
ExcludeReason = Literal["wrong_topic", "wrong_study_type", "duplicate", "language", "inaccessible", "other"]
TopicFit = Literal["same_topic", "related_topic", "different_topic", "out_of_scope"]


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


def _reason_required_on_exclude(status: str | None, reason: str | None) -> None:
    if status == "not_relevant" and not reason:
        raise ValueError("stage1_exclude_reason is required when stage1_status is not_relevant")


class HitReviewUpdate(BaseModel):
    stage1_status: Stage1Status | None = None
    stage1_exclude_reason: ExcludeReason | None = None
    stage1_note: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    topic_fit: TopicFit | None = None

    @model_validator(mode="after")
    def exclude_needs_a_reason(self):
        _reason_required_on_exclude(self.stage1_status, self.stage1_exclude_reason)
        return self


class BulkHitReviewUpdate(BaseModel):
    hit_ids: list[uuid.UUID]
    stage1_status: Stage1Status
    stage1_exclude_reason: ExcludeReason | None = None
    priority: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def exclude_needs_a_reason(self):
        _reason_required_on_exclude(self.stage1_status, self.stage1_exclude_reason)
        return self


class BulkUpdateOut(BaseModel):
    updated: int
