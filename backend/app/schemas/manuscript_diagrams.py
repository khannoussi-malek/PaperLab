import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["queued", "running", "done", "failed", "interrupted"]


class DiagramIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=10_000)  # the core names the real cap (description_invalid)
    confirm_remote: bool = False


class DiagramCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=50_000)  # the guard flags anything over its own 20 000


class DiagramErrorOut(BaseModel):
    line: int | None = Field(description="counted from the first line of the picture")
    message: str


class DiagramOut(BaseModel):
    id: uuid.UUID
    description: str
    status: Status
    code: str | None
    libraries: list[str]
    compiled: bool | None
    errors: list[DiagramErrorOut]
    labels_not_in_description: list[str]
    reason: str | None
    model: str | None
    ai: Literal[True] = True
    created_at: datetime
    updated_at: datetime
