import uuid
from datetime import datetime
from typing import Any

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


class CompileOut(BaseModel):
    state: str  # queued | again


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reason: str
    created_at: datetime
