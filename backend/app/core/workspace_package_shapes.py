"""The shape each JSON member of a workspace package must take (M35a review M2). Checked before anything is written:
a wrong type or a missing key is refused as package_invalid, never a server error. Extra keys are ignored, so a newer
PaperLab's additions still import."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator

from app.models import NoteKind, Provenance

Text = StrictStr | None
Texts = list[StrictStr] | None
Rect = Annotated[list[StrictFloat], Field(min_length=4, max_length=4)]


class _Shape(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WorkspaceMeta(_Shape):
    name: StrictStr
    description: Text = None
    research_question: Text = None
    inclusion_criteria: Text = None
    exclusion_criteria: Text = None


class Manifest(_Shape):
    format: StrictStr
    format_version: StrictInt
    created_at: StrictStr
    workspace: WorkspaceMeta


class PaperRow(_Shape):
    key: StrictStr
    title: StrictStr
    doi: Text = None
    openalex_id: Text = None
    pmid: Text = None
    pmcid: Text = None
    abstract: Text = None
    authors: Texts = None
    year: StrictInt | None = None
    venue: Text = None
    type: Text = None
    source_type: Text = None
    peer_reviewed: Text = None
    published_doi: Text = None
    published_venue: Text = None
    volume: Text = None
    issue: Text = None
    pages: Text = None
    issn: Text = None
    editors: Texts = None
    manual_fields: Texts = None
    details_source: Text = None
    field_sources: dict[StrictStr, StrictStr] | None = None
    has_pdf: StrictBool | None = None
    pdf: Text = None


class Highlight(_Shape):
    paper: StrictStr
    page: StrictInt
    rects: list[Rect]
    quoted_text: Text = None


class NoteRow(_Shape):
    body: StrictStr
    provenance: Provenance
    kind: NoteKind | None = None
    color: Text = None
    created_at: Text = None
    updated_at: Text = None
    papers: Texts = None
    highlights: list[Highlight] | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def _is_a_timestamp(cls, value: str | None) -> str | None:
        if value:
            datetime.fromisoformat(value)  # ValueError becomes a ValidationError
        return value


class TagRow(_Shape):
    name: StrictStr
    papers: Texts = None


class PapersDoc(_Shape):
    papers: list[PaperRow]


class NotesDoc(_Shape):
    notes: list[NoteRow]


class TagsDoc(_Shape):
    tags: list[TagRow]
