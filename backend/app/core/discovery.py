"""Find papers outside the library and add a free copy (M19, M19.5).

- A search asks every source that is on and answers that kind of query, at once, and merges what they find (D72,
  D73). Semantic Scholar then adds arXiv IDs and free PDF links (D70), and Unpaywall adds PDF links for DOIs still
  without one. Similar papers come from Semantic Scholar (D67).
- A source that fails is a notice; the search fails only when every source it asked failed (P7).
- Nothing found is stored: a candidate is in the library when its OpenAlex ID or DOI matches a paper (D66).
- A download counts only when the body starts with %PDF. No paywall workaround (D68).
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import papers
from app.core.candidates import (
    ARXIV_ID,
    Candidate,
    arxiv_from_doi,
    from_arxiv,
    from_core,
    from_crossref,
    from_s2,
    from_work,
    merge,
    normal_title,
    ordered_pdf_urls,
    with_s2,
)
from app.core.enrichment import ARXIV_DOI_PREFIX
from app.core.errors import Conflict
from app.core.paper_sources import KEYED, NAMES, SourceSettings
from app.models import Paper
from app.providers import arxiv, core_ac, crossref, openalex, semantic_scholar, unpaywall

logger = logging.getLogger(__name__)

PER_SOURCE = 10
SEARCH_LIMIT = 20
SIMILAR_LIMIT = 10
UNPAYWALL_CONCURRENCY = 5
MAX_PDF_BYTES = 100 * 1024 * 1024
PDF_TIMEOUT = httpx.Timeout(10.0, read=30.0)

NO_SOURCE = "No paper source that can look this up is on. Turn one on in Settings → Paper sources."
SOURCE_BUSY = "{name} is busy or unreachable."
KEY_REFUSED = "{name} refused its API key. Check it in Settings → Paper sources."
S2_OFF = "Semantic Scholar is off. Turn it on in Settings → Paper sources to see similar papers."
S2_BUSY = "Semantic Scholar is busy or unreachable. Try again in a minute."
S2_UNKNOWN = "Semantic Scholar doesn't know this paper, so it has no suggestions."
ALREADY_IN_LIBRARY = "This paper is already in your library."
NO_FREE_PDF = "No free PDF was found for this paper. Open its page, download the PDF and use Upload PDFs."

_ARXIV_QUERY = re.compile(
    rf"^(?:arxiv:|https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/)?({ARXIV_ID})(?:v\d+)?(?:\.pdf)?$", re.IGNORECASE
)
_DOI = re.compile(r"\b(10\.\d{4,9}/\S+)")
_OPENALEX_QUERY = re.compile(r"^(?:https?://(?:api\.)?openalex\.org/(?:works/)?)?(W\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class Providers:
    """The clients one request uses. A source that is off has none; Unpaywall also needs the contact email."""

    pdf: httpx.AsyncClient
    openalex: httpx.AsyncClient | None = None
    crossref: httpx.AsyncClient | None = None
    s2: httpx.AsyncClient | None = None
    arxiv: httpx.AsyncClient | None = None
    core: httpx.AsyncClient | None = None
    unpaywall: httpx.AsyncClient | None = None

    def client(self, source: str) -> httpx.AsyncClient | None:
        return self.s2 if source == "semantic_scholar" else getattr(self, source)

    async def aclose(self) -> None:
        for client in (self.pdf, self.openalex, self.crossref, self.s2, self.arxiv, self.core, self.unpaywall):
            if client is not None:
                await client.aclose()


@dataclass(frozen=True)
class SearchResult:
    results: list[Candidate]
    notices: list[str]  # one per source that failed


def build_providers(sources: SourceSettings, transport: httpx.AsyncBaseTransport | None = None) -> Providers:
    on, email, keys = sources.enabled, sources.contact_email, sources.api_keys
    return Providers(
        # No email: unlike the sources, a PDF host (arxiv.org, a publisher, a repository, or a redirect target) never
        # agreed to receive the owner's email.
        pdf=httpx.AsyncClient(
            timeout=PDF_TIMEOUT, follow_redirects=True, headers={"User-Agent": "PaperLab"}, transport=transport
        ),
        openalex=openalex.new_client(email, transport, api_key=keys["openalex"]) if on["openalex"] else None,
        crossref=crossref.new_client(email, transport) if on["crossref"] else None,
        s2=semantic_scholar.new_client(keys["semantic_scholar"], transport) if on["semantic_scholar"] else None,
        arxiv=arxiv.new_client(transport) if on["arxiv"] else None,
        core=core_ac.new_client(keys["core"], transport) if on["core"] else None,
        unpaywall=unpaywall.new_client(email, transport) if sources.unpaywall_on else None,
    )


def classify_query(query: str) -> tuple[str, str]:
    """("doi" | "arxiv" | "openalex" | "title", value). An arXiv DOI counts as its arXiv ID."""
    text = " ".join(query.split())
    if found := _ARXIV_QUERY.match(text):
        return "arxiv", found.group(1).lower()
    if work := _OPENALEX_QUERY.match(text):
        return "openalex", work.group(1).upper()
    if doi := _DOI.search(text):
        value = doi.group(1).rstrip(".,;)").lower()
        if value.startswith(ARXIV_DOI_PREFIX):
            return "arxiv", value.removeprefix(ARXIV_DOI_PREFIX)
        return "doi", value
    return "title", text


async def _openalex(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    if kind == "title":
        return [from_work(w) for w in await openalex.search_works(http, value, per_page=PER_SOURCE)]
    work = await openalex.get_work(http, f"doi:{value}" if kind == "doi" else value)
    return [from_work(work)] if work else []


async def _crossref(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    items = (
        await crossref.search(http, value, PER_SOURCE) if kind == "title" else [await crossref.get_work(http, value)]
    )
    return [candidate for item in items if item and (candidate := from_crossref(item))]


async def _semantic_scholar(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    # OpenAlex's arXiv location filter returned a wrongly merged record for BERT; Semantic Scholar's lookup didn't.
    paper = await semantic_scholar.get_paper(http, f"arXiv:{value}")
    return [from_s2(paper)] if paper else []


async def _arxiv(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    entries = await arxiv.search(http, value, PER_SOURCE) if kind == "title" else [await arxiv.get(http, value)]
    return [from_arxiv(entry) for entry in entries if entry]


async def _core(http: httpx.AsyncClient, kind: str, value: str) -> list[Candidate]:
    return [from_core(work) for work in await core_ac.search(http, value, PER_SOURCE)]


Ask = Callable[[httpx.AsyncClient, str, str], Awaitable[list[Candidate]]]
# D72: the sources each kind of query asks, most trusted first (the order results merge in).
ASKS: dict[str, dict[str, Ask]] = {
    "title": {"openalex": _openalex, "crossref": _crossref, "arxiv": _arxiv, "core": _core},
    "doi": {"openalex": _openalex, "crossref": _crossref},
    "arxiv": {"semantic_scholar": _semantic_scholar, "arxiv": _arxiv},
    "openalex": {"openalex": _openalex},
}


def _notice(source: str, error: httpx.HTTPError) -> str:
    # A source that takes no key (e.g. Crossref) can't have refused one, whatever status it answered with.
    refused = (
        source in KEYED and isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403)
    )
    return (KEY_REFUSED if refused else SOURCE_BUSY).format(name=NAMES[source])


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


async def search(session: AsyncSession, providers: Providers, query: str) -> SearchResult:
    kind, value = classify_query(query)
    asks = {source: ask for source, ask in ASKS[kind].items() if providers.client(source) is not None}
    if not asks:
        raise Conflict(NO_SOURCE)
    answers = await asyncio.gather(
        *(ask(providers.client(source), kind, value) for source, ask in asks.items()), return_exceptions=True
    )
    found: dict[str, list[Candidate]] = {}
    notices: list[str] = []
    for source, answer in zip(asks, answers):
        if isinstance(answer, httpx.HTTPError):
            logger.info("%s failed for this search: %s", source, answer)
            notices.append(_notice(source, answer))
        elif isinstance(answer, BaseException):
            raise answer
        else:
            found[source] = answer
    if not found:
        raise Conflict(" ".join(notices))
    candidates = merge(found, SEARCH_LIMIT)
    if providers.s2 is not None:
        candidates = await _add_s2_links(providers.s2, candidates)
    candidates = await _add_unpaywall_links(providers.unpaywall, candidates)
    return SearchResult(await mark_in_library(session, candidates), notices)


async def _add_s2_links(http: httpx.AsyncClient, candidates: list[Candidate]) -> list[Candidate]:
    """One batch request for the candidates Semantic Scholar didn't find itself. Never fatal: when it fails, the
    results show as they are."""
    with_doi = [c for c in candidates if c.doi and not c.s2_id]
    try:
        found = await semantic_scholar.get_papers(http, [f"DOI:{c.doi}" for c in with_doi])
    except httpx.HTTPError as exc:
        logger.info("no Semantic Scholar links for this search: %s", exc)
        return candidates
    by_doi = {c.doi: paper for c, paper in zip(with_doi, found)}
    return [with_s2(c, by_doi.get(c.doi)) for c in candidates]


async def _add_unpaywall_links(http: httpx.AsyncClient | None, candidates: list[Candidate]) -> list[Candidate]:
    """Free PDF links for candidates with a DOI and none yet: one request each, so only where a badge can change
    (D72). Never fatal: a failed lookup leaves its candidate as it is."""
    if http is None:
        return candidates
    limit = asyncio.Semaphore(UNPAYWALL_CONCURRENCY)
    unreachable = False  # set on the first connect error or timeout; a 4xx/5xx for one DOI doesn't set it

    async def with_links(candidate: Candidate) -> Candidate:
        nonlocal unreachable
        if not candidate.doi or candidate.pdf_urls or unreachable:
            return candidate
        try:
            async with limit:
                if unreachable:
                    return candidate
                urls = await unpaywall.pdf_urls(http, candidate.doi)
        except httpx.TransportError as exc:
            logger.info("Unpaywall is unreachable, skipping the rest of this search: %s", exc)
            unreachable = True
            return candidate
        except httpx.HTTPError as exc:
            logger.info("no Unpaywall links for %s: %s", candidate.doi, exc)
            return candidate
        return replace(candidate, pdf_urls=ordered_pdf_urls(candidate.arxiv_id, *urls))

    return list(await asyncio.gather(*map(with_links, candidates)))


def _same_paper_keys(title: str, *ids: str | None) -> set[str]:
    return {i.lower() for i in ids if i} | {normal_title(title)}


async def similar(
    session: AsyncSession, providers: Providers, paper: Paper, limit: int = SIMILAR_LIMIT
) -> list[Candidate]:
    if providers.s2 is None:
        raise Conflict(S2_OFF)
    doi = (paper.doi or "").lower()
    arxiv_id = arxiv_from_doi(doi)
    try:
        if arxiv_id:
            key = f"arXiv:{arxiv_id}"
        elif doi:
            key = f"DOI:{doi}"
        else:
            key = await semantic_scholar.match_title(providers.s2, paper.title)
        found = await semantic_scholar.recommend(providers.s2, key, limit + 1) if key else None
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
            raise Conflict(KEY_REFUSED.format(name=NAMES["semantic_scholar"])) from exc
        raise Conflict(S2_BUSY) from exc
    if found is None:
        raise Conflict(S2_UNKNOWN)
    own = _same_paper_keys(paper.title, doi, arxiv_id, paper.openalex_id)
    candidates = [c for c in map(from_s2, found) if not own & _same_paper_keys(c.title, c.doi, c.arxiv_id)]
    return await mark_in_library(session, await _add_unpaywall_links(providers.unpaywall, candidates[:limit]))


async def _fetch_pdf(http: httpx.AsyncClient, url: str) -> bytes | None:
    async with http.stream("GET", url) as response:
        if response.status_code != 200:
            logger.info("no PDF at %s: HTTP %d", url, response.status_code)
            return None
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) > MAX_PDF_BYTES:
                logger.info("no PDF at %s: over %d bytes", url, MAX_PDF_BYTES)
                return None
    if not body.startswith(papers.PDF_MAGIC):
        logger.info("no PDF at %s: the body is not a PDF", url)
        return None
    return bytes(body)


async def download_pdf(http: httpx.AsyncClient, urls: list[str]) -> bytes | None:
    """The first URL whose body is a PDF, in order. A failing URL moves on to the next."""
    for url in urls:
        try:
            if (data := await _fetch_pdf(http, url)) is not None:
                return data
        except httpx.HTTPError as exc:
            logger.info("no PDF at %s: %s", url, exc)
    return None


def _prefill(candidate: Candidate) -> dict[str, Any]:
    """Enrichment trusts a stored openalex_id, and a DOI only when it's locked (D69)."""
    doi = next(iter(_library_dois(candidate)), None)
    fields = {
        "title": candidate.title,
        "authors": candidate.authors,
        "year": candidate.year,
        "venue": candidate.venue,
        "cited_by_count": candidate.cited_by_count,
        "doi": doi,
        "openalex_id": candidate.openalex_id,
    }
    return fields | {"manual_fields": ["doi"]} if doi and not candidate.openalex_id else fields


def _filename(title: str) -> str:
    return f"{re.sub(r'[^\w\- ]+', '', title).strip()[:80] or 'paper'}.pdf"


async def add(session: AsyncSession, providers: Providers, candidate: Candidate, pdf_dir: Path) -> Paper:
    """Downloads the candidate's first free PDF and creates the paper. The caller enqueues ingest."""
    [marked] = await mark_in_library(session, [candidate])
    if marked.paper_id is not None:
        raise Conflict(ALREADY_IN_LIBRARY)
    # Release the connection (and its transaction) before a download that can take up to several 30s reads.
    await session.commit()
    data = await download_pdf(providers.pdf, candidate.pdf_urls)
    if data is None:
        raise Conflict(NO_FREE_PDF)
    # ponytail: two adds of one paper racing past the check above hit papers' UNIQUE doi and 500. The buttons disable
    # while adding; catch IntegrityError here if it ever happens.
    return await papers.create_paper(session, _filename(candidate.title), data, pdf_dir, prefill=_prefill(candidate))
