import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.core.lenses import LensId
from app.core.sections import Role, Source
from app.schemas.chat import ChatSource


class SectionOut(BaseModel):
    title: str | None  # null: the text before the paper's first heading
    role: Role
    source: Source  # "user": the reader fixed it
    chunk_ids: list[uuid.UUID]  # in reading order
    first_chunk_id: uuid.UUID
    page: int
    preview: str


class LensOut(BaseModel):
    id: LensId
    label: str
    chunk_ids: list[uuid.UUID]  # in reading order; empty: the paper has no sections for this lens
    positional_fallback: bool  # Key ideas shows the start and end of the paper
    missing_roles: list[Role]


class SectionsOut(BaseModel):
    sections: list[SectionOut]
    lenses: list[LensOut]


class SectionRoleIn(BaseModel):
    section_title: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    role: Role | None  # null: back to the automatic role


class BriefOut(BaseModel):
    id: uuid.UUID
    lens: LensId
    content: str
    model: str
    connection_name: str | None
    prompt_version: int
    created_at: datetime
    stale: bool  # the lens's chunks changed since it was written: a role fix or a re-ingest
    partial: bool  # written from the start of the lens only: the rest didn't fit
    # sources[i] is C{i+1}. null: a re-ingest replaced that chunk, so its marker renders as plain text.
    sources: list[ChatSource | None]
