"""Find papers outside the library and add a free copy (M19).

- OpenAlex answers title and DOI searches; Semantic Scholar answers arXiv IDs, similar papers, and fills in the arXiv
  IDs and free PDF links OpenAlex lacks (D67, D70).
- Nothing found is stored: a candidate is in the library when its OpenAlex ID or DOI matches a paper (D66).
- A download counts only when the body starts with %PDF. No paywall workaround (D68).
"""

import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from app.core.enrichment import ARXIV_DOI_PREFIX, short_id

_ARXIV_ID = r"\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7}"
_ARXIV_QUERY = re.compile(
    rf"^(?:arxiv:|https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/)?({_ARXIV_ID})(?:v\d+)?(?:\.pdf)?$", re.IGNORECASE
)
_ARXIV_URL = re.compile(rf"arxiv\.org/(?:abs|pdf)/({_ARXIV_ID})", re.IGNORECASE)
_DOI = re.compile(r"\b(10\.\d{4,9}/\S+)")
_OPENALEX_QUERY = re.compile(r"^(?:https?://(?:api\.)?openalex\.org/(?:works/)?)?(W\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    """A paper found outside the library. `paper_id` is set when the library already holds it."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    cited_by_count: int | None = None
    pdf_urls: list[str] = field(default_factory=list)
    paper_id: uuid.UUID | None = None


def classify_query(query: str) -> tuple[str, str]:
    """("doi" | "arxiv" | "openalex" | "title", value). An arXiv DOI counts as its arXiv ID."""
    text = " ".join(query.split())
    if arxiv := _ARXIV_QUERY.match(text):
        return "arxiv", arxiv.group(1).lower()
    if work := _OPENALEX_QUERY.match(text):
        return "openalex", work.group(1).upper()
    if doi := _DOI.search(text):
        value = doi.group(1).rstrip(".,;)").lower()
        if value.startswith(ARXIV_DOI_PREFIX):
            return "arxiv", value.removeprefix(ARXIV_DOI_PREFIX)
        return "doi", value
    return "title", text


def _arxiv_from_doi(doi: str | None) -> str | None:
    return doi.removeprefix(ARXIV_DOI_PREFIX) if doi and doi.startswith(ARXIV_DOI_PREFIX) else None


def _arxiv_from_url(url: str | None) -> str | None:
    match = _ARXIV_URL.search(url or "")
    return match.group(1).lower() if match else None


def _pdf_urls(arxiv_id: str | None, *links: str | None) -> list[str]:
    """arXiv first, then `links` in order: deduplicated, http(s) only (D68)."""
    urls = [f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None, *links]
    return list(dict.fromkeys(url for url in urls if url and url.startswith(("http://", "https://"))))


def from_work(work: dict[str, Any]) -> Candidate:
    doi = (work.get("doi") or "").removeprefix("https://doi.org/").lower() or None
    best = work.get("best_oa_location") or {}
    locations = work.get("locations") or []
    location_urls = [
        url for place in [best, *locations] for url in (place.get("landing_page_url"), place.get("pdf_url"))
    ]
    arxiv_id = _arxiv_from_doi(doi) or next(filter(None, map(_arxiv_from_url, location_urls)), None)
    source = (work.get("primary_location") or {}).get("source") or {}
    return Candidate(
        title=work.get("title") or "Untitled",
        authors=[a["author"]["display_name"] for a in work.get("authorships") or [] if a.get("author")],
        year=work.get("publication_year"),
        venue=source.get("display_name"),
        doi=doi,
        arxiv_id=arxiv_id,
        openalex_id=short_id(work.get("id")),
        cited_by_count=work.get("cited_by_count"),
        pdf_urls=_pdf_urls(arxiv_id, best.get("pdf_url"), *(place.get("pdf_url") for place in locations)),
    )


def from_s2(paper: dict[str, Any]) -> Candidate:
    ids = paper.get("externalIds") or {}
    doi = (ids.get("DOI") or "").lower() or None
    arxiv_id = (ids.get("ArXiv") or "").lower() or _arxiv_from_doi(doi)
    return Candidate(
        title=paper.get("title") or "Untitled",
        authors=[a["name"] for a in paper.get("authors") or [] if a.get("name")],
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        doi=doi,
        arxiv_id=arxiv_id,
        s2_id=paper.get("paperId"),
        cited_by_count=paper.get("citationCount"),
        pdf_urls=_pdf_urls(arxiv_id, (paper.get("openAccessPdf") or {}).get("url")),
    )


def with_s2(candidate: Candidate, paper: dict[str, Any] | None) -> Candidate:
    """An OpenAlex candidate with Semantic Scholar's arXiv ID and free PDF link added (D70)."""
    if paper is None:
        return candidate
    found = from_s2(paper)
    arxiv_id = candidate.arxiv_id or found.arxiv_id
    return replace(
        candidate,
        arxiv_id=arxiv_id,
        s2_id=found.s2_id,
        pdf_urls=_pdf_urls(arxiv_id, *found.pdf_urls, *candidate.pdf_urls),
    )
