"""What importing a Zotero export answers (M40 Task 9a), over the API and MCP."""

import uuid
from typing import Literal

from pydantic import BaseModel


class NeedsPdfOut(BaseModel):
    """An entry with no PDF in the zip and no free copy found: the whole parsed reference (so it can later be saved as
    a metadata-only paper as it is), with what was tried and where a free copy may be."""

    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    issn: str | None = None
    abstract: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    editors: list[str] = []
    source_type: str = "other"
    tags: list[str] = []
    notes: list[str] = []  # markdown
    tried: list[dict[str, str]] = []  # {url, outcome}
    free_copies: list[str] = []


class FailedOut(BaseModel):
    title: str
    reason: str


class ImportResultOut(BaseModel):
    imported: int  # new papers
    already_in_library: int
    pdfs_attached: int  # new papers whose PDF came from the zip
    notes: int
    needs_pdf: list[NeedsPdfOut]
    failed: list[FailedOut]
    not_reached: list[str]  # titles left when the import ran out of time
    stopped: str  # why it stopped early, in words; "" when every entry was reached


class ImportCountsOut(BaseModel):
    """A running import's tallies; `done` counts the entries reached."""

    total: int
    done: int
    imported: int
    already_in_library: int
    pdfs_attached: int
    notes: int
    needs_pdf: int
    failed: int


class ImportPreviewOut(BaseModel):
    """What an import would do, before it starts; nothing is created and no paper source is contacted."""

    total: int
    already_in_library: int
    with_bundled_pdf: int
    would_fetch: int  # entries that will contact free-copy sources
    cannot_import_without_fetch: int
    disclosure: str | None  # the sentence to show when would_fetch > 0


class ImportProgressOut(BaseModel):
    """An import, finished inline or as a job. `result` once finished, `counts` while running, `message` (in words)
    when failed, restarted or expired."""

    state: Literal["queued", "running", "finished", "failed", "restarted", "expired"]
    job_id: str | None = None
    workspace_id: uuid.UUID | None = None  # the workspace imported into, when the import named or made one
    counts: ImportCountsOut | None = None
    result: ImportResultOut | None = None
    message: str | None = None
