from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckInfoOut(BaseModel):
    name: str
    cost: Literal["cheap", "full"]
    description: str


class RunChecksIn(BaseModel):
    """`cost: "full"` means no cost filter (all checks); it exists so the body reads clearly."""

    model_config = ConfigDict(extra="forbid")

    names: list[str] | None = Field(None, min_length=1)  # only these checks; unknown name -> 422 unknown_check
    cost: Literal["cheap", "full"] | None = None  # "cheap" = only cheap checks; None/"full" = all


class FindingOut(BaseModel):
    check: str
    severity: Literal["error", "warning", "info"]
    file: str | None
    line: int | None
    message: str
    fix_hint: str | None


class RunChecksOut(BaseModel):
    ran: list[str]
    findings: list[FindingOut]
    counts: dict[str, int]
