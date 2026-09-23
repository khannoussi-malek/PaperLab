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
