import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class TemplateOut(BaseModel):
    name: str
    label: str


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str
    size: int
    updated_at: datetime


class FileTextOut(BaseModel):
    path: str
    text: str
    updated_at: datetime


class ManuscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID | None
    title: str
    main_file: str
    checklist: dict[str, Any]
    compile_status: str
    compile_requested: bool
    compiled_at: datetime | None
    compile_log: str | None
    compile_friendly: str | None
    compile_errors: list[Any]
    created_at: datetime
    updated_at: datetime


class ManuscriptDetailOut(ManuscriptOut):
    files: list[FileOut]


class ManuscriptImportOut(ManuscriptDetailOut):
    skipped: list[str]  # members of a type a manuscript can't hold, left out


class ManuscriptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    template: str
    workspace_id: uuid.UUID | None = None


class ManuscriptPatch(BaseModel):
    """Send only what changes: workspace_id null moves the manuscript out of its workspace."""
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)  # null is refused below, as for main_file and checklist
    workspace_id: uuid.UUID | None = None
    main_file: str | None = None
    checklist: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _no_nulls(self):
        for name in ("title", "main_file", "checklist"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class FilePut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    base_updated_at: AwareDatetime | None = None  # the updated_at the editor last saw; omitted for a new file


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_path: str


class SectionAddIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    after: str | None = None


class SectionTitleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str


class SectionMoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: int = Field(ge=0)


class SectionPathOut(BaseModel):
    path: str


class SectionPathsOut(BaseModel):
    paths: list[str]


class CompileOut(BaseModel):
    state: str  # queued | again


class SyncPointOut(BaseModel):
    page: int
    x: float
    y: float


class SyncSourceOut(BaseModel):
    file: str
    line: int


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reason: str
    created_at: datetime


class CitablePaperOut(BaseModel):
    paper_id: uuid.UUID
    key: str
    pinned: bool
    title: str
    first_author: str | None
    year: int | None
    has_pdf: bool
    notes: int
    highlights: int
    ai_notes: int


class PinKeyOut(BaseModel):
    key: str


class RankIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=20_000)


class RankOut(BaseModel):
    paper_ids: list[uuid.UUID]


class EvidenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(max_length=20_000)  # the core says what is too long, with its own code
    confirm_remote: bool = False


class EvidencePassageOut(BaseModel):
    chunk_id: uuid.UUID
    page: int
    text: str


class EvidencePaperOut(BaseModel):
    paper_id: uuid.UUID
    key: str
    passages: list[EvidencePassageOut]


class EvidenceFoundOut(BaseModel):
    sentence_hash: str
    papers: list[EvidencePaperOut]
    verdicts: Literal["queued", "unavailable"]


class EvidenceRowOut(BaseModel):
    paper_id: uuid.UUID
    rank: int
    status: Literal["queued", "running", "done", "failed", "interrupted"]
    verdict: str | None
    reason: str | None
    quote: str | None
    page: int | None
    output_id: uuid.UUID | None


class MissingKeyOut(BaseModel):
    key: str
    file: str
    line: int
