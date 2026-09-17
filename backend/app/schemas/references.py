import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

Direction = Literal["cites", "cited_by"]
ReferencesState = Literal["none", "fetching", "ready", "failed"]


class ReferenceOut(BaseModel):
    """A reference or citing work, ranked for this library. `cocitation` counts the library papers linked to it the
    same way; `paper_id` is set when the library holds it. Never a vector."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    openalex_id: str | None
    s2_id: str | None
    cited_by_count: int | None
    has_pdf: bool
    cocitation: int
    paper_id: uuid.UUID | None
    position: int


class ReferencesSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cited_by_3plus: int
    with_pdf: int


class ReferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: ReferencesState
    error: str | None
    direction: Direction
    summary: ReferencesSummary
    rows: list[ReferenceOut]


class RefreshOut(BaseModel):
    state: ReferencesState


class ImportReferenceIn(BaseModel):
    # Also file the new paper in this workspace (404 before any download when it's unknown).
    workspace_id: uuid.UUID | None = None
