"""Request and response models for /api/skills (M17 spec §6). Field limits are enforced by core.skills."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.lenses import LensId

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
    lens: LensId  # the lens the skill's answers read through; 'full' is the whole paper


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    description: str = ""
    scope: Scope
    instructions: str
    lens: LensId | None = None  # omitted: 'full'


class SkillUpdate(BaseModel):
    """Only the fields sent change. An explicit null is refused by the service, not here."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    scope: Scope | None = None
    instructions: str | None = None
    is_listed: bool | None = None
    lens: LensId | None = None


class SkillDefaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ChatKind
    on: bool
