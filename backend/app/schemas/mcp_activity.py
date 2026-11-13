from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    tool: str
    arguments: str  # a summary, never the full arguments
    outcome: str
    duration_ms: int
    is_write: bool


class WritesSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    writes_enabled: bool


class WritesSettingOut(BaseModel):
    writes_enabled: bool
