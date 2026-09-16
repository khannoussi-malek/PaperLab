"""Find papers outside the library and add a free copy (M19).

- OpenAlex answers title and DOI searches; Semantic Scholar answers arXiv IDs, similar papers, and fills in the arXiv
  IDs and free PDF links OpenAlex lacks (D67, D70).
- Nothing found is stored: a candidate is in the library when its OpenAlex ID or DOI matches a paper (D66).
- A download counts only when the body starts with %PDF. No paywall workaround (D68).
"""

import logging
import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enrichment import ARXIV_DOI_PREFIX, short_id
from app.core.errors import Conflict
from app.models import Paper
from app.providers import openalex, semantic_scholar

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 10
SIMILAR_LIMIT = 10
PDF_TIMEOUT = httpx.Timeout(10.0, read=30.0)

OPENALEX_OFF = "OpenAlex is off. Set OPENALEX_MAILTO in .env to search by title or DOI."
OPENALEX_BUSY = "OpenAlex is busy or unreachable. Try again in a minute."
S2_BUSY = "Semantic Scholar is busy or unreachable. Try again in a minute."
S2_UNKNOWN = "Semantic Scholar doesn't know this paper, so it has no suggestions."

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


@dataclass(frozen=True)
class Providers:
    """The clients one request uses. `openalex` is None when OPENALEX_MAILTO is empty."""

    openalex: httpx.AsyncClient | None
    s2: httpx.AsyncClient
    pdf: httpx.AsyncClient

    async def aclose(self) -> None:
        for client in (self.openalex, self.s2, self.pdf):
            if client is not None:
                await client.aclose()


def build_providers(mailto: str, s2_api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> Providers:
    agent = f"PaperLab (mailto:{mailto})" if mailto else "PaperLab"
    return Providers(
        openalex=openalex.new_client(mailto, transport) if mailto else None,
        s2=semantic_scholar.new_client(s2_api_key, transport),
        pdf=httpx.AsyncClient(
            timeout=PDF_TIMEOUT, follow_redirects=True, headers={"User-Agent": agent}, transport=transport
        ),
    )


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


def _library_dois(candidate: Candidate) -> list[str]:
    """Lowercase: a candidate the API received may spell its DOI in any case."""
    arxiv_doi = candidate.arxiv_id and f"{ARXIV_DOI_PREFIX}{candidate.arxiv_id}"
    return [doi.lower() for doi in (candidate.doi, arxiv_doi) if doi]


async def mark_in_library(session: AsyncSession, candidates: list[Candidate]) -> list[Candidate]:
    """New candidates with `paper_id` set where the library holds the paper, by OpenAlex ID or DOI (any case)."""
    ids = [c.openalex_id for c in candidates if c.openalex_id]
    dois = [doi for c in candidates for doi in _library_dois(c)]
    rows = (
        await session.execute(
            select(Paper.id, func.lower(Paper.doi), Paper.openalex_id).where(
                or_(Paper.openalex_id.in_(ids), func.lower(Paper.doi).in_(dois))
            )
        )
    ).all()
    library = {key: paper_id for paper_id, doi, openalex_id in rows for key in (doi, openalex_id) if key}
    return [
        replace(c, paper_id=next((library[k] for k in (c.openalex_id, *_library_dois(c)) if k in library), None))
        for c in candidates
    ]


async def search(session: AsyncSession, providers: Providers, query: str, limit: int = SEARCH_LIMIT) -> list[Candidate]:
    kind, value = classify_query(query)
    if kind == "arxiv":
        # OpenAlex's arXiv location filter returned a wrongly merged record for BERT; Semantic Scholar's lookup didn't.
        try:
            paper = await semantic_scholar.get_paper(providers.s2, f"arXiv:{value}")
        except httpx.HTTPError as exc:
            raise Conflict(S2_BUSY) from exc
        return await mark_in_library(session, [from_s2(paper)] if paper else [])
    if providers.openalex is None:
        raise Conflict(OPENALEX_OFF)
    try:
        if kind == "title":
            works = await openalex.search_works(providers.openalex, value, per_page=limit)
        else:
            work = await openalex.get_work(providers.openalex, f"doi:{value}" if kind == "doi" else value)
            works = [work] if work else []
    except httpx.HTTPError as exc:
        raise Conflict(OPENALEX_BUSY) from exc
    return await mark_in_library(session, await _add_s2_links(providers.s2, [from_work(w) for w in works]))


async def _add_s2_links(http: httpx.AsyncClient, candidates: list[Candidate]) -> list[Candidate]:
    """One batch request. Never fatal: when Semantic Scholar fails, OpenAlex's results show as they are."""
    with_doi = [c for c in candidates if c.doi]
    try:
        found = await semantic_scholar.get_papers(http, [f"DOI:{c.doi}" for c in with_doi])
    except httpx.HTTPError as exc:
        logger.info("no Semantic Scholar links for this search: %s", exc)
        return candidates
    by_doi = {c.doi: paper for c, paper in zip(with_doi, found)}
    return [with_s2(c, by_doi.get(c.doi)) for c in candidates]


def _same_paper_keys(title: str, *ids: str | None) -> set[str]:
    return {i.lower() for i in ids if i} | {re.sub(r"\W+", " ", title).strip().casefold()}


async def similar(
    session: AsyncSession, providers: Providers, paper: Paper, limit: int = SIMILAR_LIMIT
) -> list[Candidate]:
    doi = (paper.doi or "").lower()
    arxiv_id = _arxiv_from_doi(doi)
    try:
        if arxiv_id:
            key = f"arXiv:{arxiv_id}"
        elif doi:
            key = f"DOI:{doi}"
        else:
            key = await semantic_scholar.match_title(providers.s2, paper.title)
        found = await semantic_scholar.recommend(providers.s2, key, limit + 1) if key else None
    except httpx.HTTPError as exc:
        raise Conflict(S2_BUSY) from exc
    if found is None:
        raise Conflict(S2_UNKNOWN)
    own = _same_paper_keys(paper.title, doi, arxiv_id, paper.openalex_id)
    candidates = [c for c in map(from_s2, found) if not own & _same_paper_keys(c.title, c.doi, c.arxiv_id)]
    return await mark_in_library(session, candidates[:limit])
