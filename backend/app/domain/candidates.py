"""A paper found outside the library, and the limits a candidate is held to."""

import uuid
from dataclasses import dataclass, field

# CandidateIn (app/schemas/discovery.py) rejects a candidate over either limit with 422; capping here first means
# the Add button never shows for a candidate its own endpoint would then refuse.
MAX_PDF_URLS = 10
MAX_AUTHORS = 500


@dataclass(frozen=True)
class Candidate:
    """A paper found outside the library. `sources` lists every source that found it, most trusted first; `paper_id`
    is set when the library already holds it. `external_ids` (Phase 0b) is keyed by the registry's own source ids
    ("openalex", "semantic_scholar", "arxiv", "core", "pubmed") — a source with no id for this paper has no key,
    never a key mapped to None."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    cited_by_count: int | None = None
    abstract: str | None = None
    pdf_urls: list[str] = field(default_factory=list)
    sources: tuple[str, ...] = ()
    paper_id: uuid.UUID | None = None
    # M59 hit triage: what kind of source this is and, for a preprint with a published version, where it appeared.
    source_type: str | None = None
    published_doi: str | None = None
    published_venue: str | None = None
