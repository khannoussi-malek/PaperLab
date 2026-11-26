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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers import papers
from app.core.papers.enrichment import ARXIV_DOI_PREFIX
from app.core.papers.paper_sources import KEYED, NAMES
from app.core.papers.provenance import sources_of
from app.core.search import landing_page
from app.core.search.candidates import ARXIV_ID, arxiv_from_doi, arxiv_from_url, merge, normal_title, ordered_pdf_urls
from app.core.search.free_copy import (
    ALREADY_IN_LIBRARY,
    _arxiv_ids,
    _download_free_copy,
    _reuse_arxiv_copy,
    _reuse_published_copy,
    _unpaywall_lookup,
    details_source,
)
from app.core.search.from_indexes import from_s2, with_s2
from app.core.search.source_clients import Providers
from app.core.search.source_registry import ASKS
from app.domain.candidates import Candidate
from app.domain.errors import Conflict
from app.models import Paper
from app.providers import pmc_opendata, semantic_scholar, unpaywall

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 20
SIMILAR_LIMIT = 10
UNPAYWALL_CONCURRENCY = 5

NO_SOURCE = "No paper source that can look this up is on. Turn one on in Settings → Paper sources."
SOURCE_BUSY = "{name} is busy or unreachable."
KEY_REFUSED = "{name} refused its API key. Check it in Settings → Paper sources."
S2_OFF = "Semantic Scholar is off. Turn it on in Settings → Paper sources to see similar papers."
S2_BUSY = "Semantic Scholar is busy or unreachable. Try again in a minute."
S2_UNKNOWN = "Semantic Scholar doesn't know this paper, so it has no suggestions."
NO_FREE_PDF = "No free PDF was found for this paper. Open its page, download the PDF and use Upload PDFs."

_ARXIV_QUERY = re.compile(
    rf"^(?:arxiv:|https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/)?({ARXIV_ID})(?:v\d+)?(?:\.pdf)?$", re.IGNORECASE
)
_DOI = re.compile(r"\b(10\.\d{4,9}/\S+)")
_OPENALEX_QUERY = re.compile(r"^(?:https?://(?:api\.)?openalex\.org/(?:works/)?)?(W\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class SearchResult:
    results: list[Candidate]
    notices: list[str]  # one per source that failed


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


def notice(source: str, error: httpx.HTTPError) -> str:
    # A source that takes no key (e.g. Crossref) can't have refused one, whatever status it answered with.
    refused = (
        source in KEYED and isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403)
    )
    return (KEY_REFUSED if refused else SOURCE_BUSY).format(name=NAMES[source])


def _library_dois(candidate: Candidate) -> list[str]:
    """Lowercase: a candidate the API received may spell its DOI in any case."""
    arxiv_id = candidate.external_ids.get("arxiv")
    arxiv_doi = arxiv_id and f"{ARXIV_DOI_PREFIX}{arxiv_id}"
    return [doi.lower() for doi in (candidate.doi, arxiv_doi) if doi]


async def mark_in_library(session: AsyncSession, candidates: list[Candidate]) -> list[Candidate]:
    """New candidates with `paper_id` set where the library holds the paper, by OpenAlex ID or DOI (any case); a
    preprint copy also answers to its published DOI."""
    ids = [oa for c in candidates if (oa := c.external_ids.get("openalex"))]
    dois = [doi for c in candidates for doi in _library_dois(c)]
    rows = (
        await session.execute(
            select(Paper.id, func.lower(Paper.doi), Paper.openalex_id, func.lower(Paper.published_doi)).where(
                or_(
                    Paper.openalex_id.in_(ids),
                    func.lower(Paper.doi).in_(dois),
                    func.lower(Paper.published_doi).in_(dois),
                )
            )
        )
    ).all()
    library = {key: paper_id for paper_id, *keys in rows for key in keys if key}
    return [
        replace(
            c,
            paper_id=next(
                (library[k] for k in (c.external_ids.get("openalex"), *_library_dois(c)) if k in library), None
            ),
        )
        for c in candidates
    ]


async def search(session: AsyncSession, providers: Providers, query: str) -> SearchResult:
    kind, value = classify_query(query)
    if kind == "title" and landing_page.is_link(query):
        # a link with no DOI or ID in it: its page says which paper it is
        kind, value = classify_query(await _from_page(providers, query.strip()))
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
            notices.append(notice(source, answer))
        elif isinstance(answer, BaseException):
            raise answer
        else:
            found[source] = answer
    if not found:
        raise Conflict(" ".join(notices))
    candidates = merge(found, SEARCH_LIMIT)
    if (s2 := providers.client("semantic_scholar")) is not None:
        candidates = await _add_s2_links(s2, candidates)
    candidates = await _add_unpaywall_links(providers.client("unpaywall"), candidates)
    return SearchResult(await mark_in_library(session, candidates), notices)


async def _from_page(providers: Providers, url: str) -> str:
    """What a paper's page says it is (DOI, arXiv ID or title), to search for. Conflict with why when it can't be read
    or says nothing."""
    try:
        page = await landing_page.read(providers.pdf, url)
    except landing_page.PageUnreadable as exc:
        logger.info("couldn't read %s: %s", url, exc)
        raise Conflict(str(exc)) from exc
    found = landing_page.identify(page)
    if found is None:
        raise Conflict(landing_page.SAYS_NOTHING)
    return found


async def _add_s2_links(http: httpx.AsyncClient, candidates: list[Candidate]) -> list[Candidate]:
    """One batch request for the candidates Semantic Scholar didn't find itself. Never fatal: when it fails, the
    results show as they are."""
    with_doi = [c for c in candidates if c.doi and not c.external_ids.get("semantic_scholar")]
    try:
        found = await semantic_scholar.get_papers(http, [f"DOI:{c.doi}" for c in with_doi])
    except httpx.HTTPError as exc:
        logger.info("no Semantic Scholar links for this search: %s", exc)
        return candidates
    by_doi = {c.doi: paper for c, paper in zip(with_doi, found)}
    return [with_s2(c, by_doi.get(c.doi)) for c in candidates]


async def _add_unpaywall_links(
    http: httpx.AsyncClient | None, candidates: list[Candidate], merge: bool = False
) -> list[Candidate]:
    """Unpaywall's free PDF links for candidates with a DOI and no PDF link (D72), one request each. `merge` also asks
    for those that have one and merges the answer in (M63: OpenAlex alone often lists only a bot-checked publisher);
    add() uses it for the one candidate being added. Never fatal: a failed lookup leaves its candidate as it is."""
    if http is None:
        return candidates
    limit = asyncio.Semaphore(UNPAYWALL_CONCURRENCY)
    unreachable = False  # set on the first connect error or timeout; a 4xx/5xx for one DOI doesn't set it

    async def with_links(candidate: Candidate) -> Candidate:
        nonlocal unreachable
        if not candidate.doi or unreachable or (candidate.pdf_urls and not merge):
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
        merged = ordered_pdf_urls(candidate.external_ids.get("arxiv"), *candidate.pdf_urls, *urls)
        return replace(candidate, pdf_urls=merged)

    return list(await asyncio.gather(*map(with_links, candidates)))


def _same_paper_keys(title: str, *ids: str | None) -> set[str]:
    return {i.lower() for i in ids if i} | {normal_title(title)}


async def s2_key(http: httpx.AsyncClient, doi: str | None, title: str) -> str | None:
    """The key Semantic Scholar knows something by: `arXiv:<id>` for an arXiv DOI, `DOI:<doi>`, else its best
    title match (one request). None when it has no match. Raises httpx.HTTPError. Takes doi/title directly (not a
    Paper) so it works for anything with these two fields — an imported Paper or a not-yet-imported hit's own
    ExternalRef alike (snowball's own use, workspace_search.py)."""
    doi = (doi or "").lower()
    if arxiv_id := arxiv_from_doi(doi):
        return f"arXiv:{arxiv_id}"
    if doi:
        return f"DOI:{doi}"
    return await semantic_scholar.match_title(http, title)


async def similar(
    session: AsyncSession, providers: Providers, paper: Paper, limit: int = SIMILAR_LIMIT
) -> list[Candidate]:
    if (s2 := providers.client("semantic_scholar")) is None:
        raise Conflict(S2_OFF)
    doi = (paper.doi or "").lower()
    arxiv_id = arxiv_from_doi(doi)
    try:
        key = await s2_key(s2, paper.doi, paper.title)
        found = await semantic_scholar.recommend(s2, key, limit + 1) if key else None
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
            raise Conflict(KEY_REFUSED.format(name=NAMES["semantic_scholar"])) from exc
        raise Conflict(S2_BUSY) from exc
    if found is None:
        raise Conflict(S2_UNKNOWN)
    own = _same_paper_keys(paper.title, doi, arxiv_id, paper.openalex_id)
    candidates = [
        c for c in map(from_s2, found) if not own & _same_paper_keys(c.title, c.doi, c.external_ids.get("arxiv"))
    ]
    return await mark_in_library(session, await _add_unpaywall_links(providers.client("unpaywall"), candidates[:limit]))


def prefill(candidate: Candidate) -> dict[str, Any]:
    """Enrichment trusts a stored openalex_id, and a DOI only when it's locked (D69). The title is always locked:
    ingest's PDF-font heuristic and enrichment's metadata are both worse than the title the source already gave us,
    so it must survive both (M7.5). field_sources stamps the groups it fills with the candidate's source (R22)."""
    doi = next(iter(_library_dois(candidate)), None)
    openalex_id = candidate.external_ids.get("openalex")
    fields = {
        "title": candidate.title,
        "authors": candidate.authors,
        "year": candidate.year,
        "venue": candidate.venue,
        "abstract": candidate.abstract,
        "cited_by_count": candidate.cited_by_count,
        "doi": doi,
        "openalex_id": openalex_id,
    }
    locked = ["doi", "title"] if doi and not openalex_id else ["title"]
    return fields | {"manual_fields": locked, "field_sources": sources_of(fields, details_source(candidate))}


def _filename(title: str) -> str:
    return f"{re.sub(r'[^\w\- ]+', '', title).strip()[:80] or 'paper'}.pdf"


def candidate_of(paper: Paper) -> Candidate:
    """A held paper as find_pdf's candidate, `paper_id` set to it: its bibliographic fields, its OpenAlex, PMC and
    arXiv ids, and the arXiv PDF and open-access link it knows, as its first PDF URLs."""
    arxiv_id = arxiv_from_doi((paper.doi or "").lower() or None) or arxiv_from_url(paper.oa_url)
    pmc = pmc_opendata.normalize(paper.pmcid)
    ids = {"openalex": paper.openalex_id, "pmc": pmc and pmc.removeprefix("PMC"), "arxiv": arxiv_id}
    return Candidate(
        title=paper.title,
        authors=list(paper.authors or []),
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        external_ids={key: value for key, value in ids.items() if value},
        pdf_urls=ordered_pdf_urls(arxiv_id, paper.oa_url),
        paper_id=paper.id,
    )


@dataclass(frozen=True)
class Added:
    paper: Paper
    tried: list[dict]  # what each URL said (a failure carries it on the Conflict)
    copies: list[str]  # repository pages that may hold a copy


async def add(
    session: AsyncSession, providers: Providers, candidate: Candidate, pdf_dir: Path, save_without_pdf: bool = False
) -> Paper:
    """add_traced, for a caller that only wants the paper."""
    return (await add_traced(session, providers, candidate, pdf_dir, save_without_pdf)).paper


async def add_traced(
    session: AsyncSession, providers: Providers, candidate: Candidate, pdf_dir: Path, save_without_pdf: bool = False
) -> Added:
    """Downloads the candidate's first free PDF and creates the paper, with what each URL said and the repository
    pages that may hold a copy. The caller enqueues ingest.

    With `save_without_pdf`, no free PDF saves a PDF-less paper instead of raising NO_FREE_PDF: the caller enqueues
    index_abstract when it has an abstract."""
    [marked] = await mark_in_library(session, [candidate])
    if marked.paper_id is not None:
        raise Conflict(ALREADY_IN_LIBRARY, paper_id=marked.paper_id)
    # Release the connection (and its transaction) before a download that can take up to several 30s reads.
    await session.commit()
    await _reuse_published_copy(session, candidate)  # the reverse: its published version is held
    # One request of its own: a repository copy beside a bot-checked publisher, and a recorded answer in `tried`.
    candidate, lookups = await _unpaywall_lookup(providers, candidate)
    await _reuse_arxiv_copy(session, candidate, _arxiv_ids(candidate), [])  # before any download
    data, tried, copies = await _download_free_copy(session, providers, candidate, lookups)
    if data is None and save_without_pdf:
        source = details_source(candidate)
        paper = await papers.create_metadata_paper(session, prefill(candidate), source, looked_for_pdf=True)
        return Added(paper, tried, copies)
    if data is None:
        raise Conflict(NO_FREE_PDF, tried=tried, free_copies=copies)
    # ponytail: two adds of one paper racing past the check above hit papers' UNIQUE doi and 500. The buttons disable
    # while adding; catch IntegrityError here if it ever happens.
    paper = await papers.create_paper(session, _filename(candidate.title), data, pdf_dir, prefill=prefill(candidate))
    return Added(paper, tried, copies)
