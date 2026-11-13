"""Request and response models for /api/skills (M17 spec §6). Field limits are enforced by core.skills."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Scope = Literal["paper", "workspace", "both"]
ChatKind = Literal["paper", "workspace"]


class SkillOut(BaseModel):
    id: str  # builtin:<slug> or custom:<uuid>
    label: str
    description: str
    scope: Scope
    instructions: str
    version: int
    is_listed: bool
    is_paper_default: bool
    is_workspace_default: bool
    state: Literal["builtin", "edited", "custom"]


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    description: str = ""
    scope: Scope
    instructions: str


class SkillUpdate(BaseModel):
    """Only the fields sent change. An explicit null is refused by the service, not here."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    scope: Scope | None = None
    instructions: str | None = None
    is_listed: bool | None = None


class SkillDefaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ChatKind
    on: bool
