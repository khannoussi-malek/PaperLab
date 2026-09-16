import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.core.discovery import Candidate

AuthorName = Annotated[str, Field(min_length=1, max_length=300)]


class CandidateOut(BaseModel):
    """A paper found outside the library. `paper_id` is set when the library already holds it."""

    model_config = ConfigDict(from_attributes=True)

    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    openalex_id: str | None
    s2_id: str | None
    cited_by_count: int | None
    pdf_urls: list[str]
    paper_id: uuid.UUID | None


class CandidateIn(BaseModel):
    """A search result or suggestion sent back to be added. Extra fields (its `paper_id`) are ignored: the library
    is checked again."""

    title: str = Field(min_length=1, max_length=1000)
    authors: list[AuthorName] = Field(default_factory=list, max_length=500)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = Field(default=None, max_length=1000)
    doi: str | None = Field(default=None, pattern=r"^10\.\d{4,9}/\S+$", max_length=300)
    arxiv_id: str | None = Field(default=None, pattern=r"^(\d{4}\.\d{4,5}|[A-Za-z-]+(\.[A-Za-z]{2})?/\d{7})$")
    openalex_id: str | None = Field(default=None, pattern=r"^W\d+$", max_length=20)
    s2_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    cited_by_count: int | None = Field(default=None, ge=0)
    pdf_urls: list[HttpUrl] = Field(default_factory=list, max_length=10)

    def to_candidate(self) -> Candidate:
        return Candidate(**self.model_dump(exclude={"pdf_urls"}), pdf_urls=[str(url) for url in self.pdf_urls])


class AddPaperRequest(BaseModel):
    candidate: CandidateIn
    # Also file the new paper in this workspace (404 before any download when it's unknown).
    workspace_id: uuid.UUID | None = None
