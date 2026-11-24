"""Finding a free PDF for a paper: a copy the library already holds, Unpaywall, arXiv, DiVA and PMC."""

import asyncio
import logging
import re
import time
import uuid
from dataclasses import replace
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.papers.enrichment import ARXIV_DOI_PREFIX
from app.core.papers.paper_enrichment import apply_published
from app.core.platform.redact import redact
from app.core.search import pdf_download
from app.core.search.candidates import arxiv_from_doi, arxiv_from_url, normal_title, ordered_pdf_urls, surname
from app.core.search.same_work import _has_arxiv_id, _renamed_work, _title_prefix, same_work
from app.core.search.source_clients import Providers
from app.domain.candidates import Candidate
from app.domain.errors import Conflict, InvalidInput
from app.domain.source_types import DETAILS_SOURCES, is_preprint_copy
from app.models import Paper
from app.providers import arxiv, europe_pmc, pmc_opendata, unpaywall

logger = logging.getLogger(__name__)

ALREADY_IN_LIBRARY = "This paper is already in your library."


def details_source(candidate: Candidate) -> str:
    """The first of the candidate's sources that is a details source, else "search"."""
    return next((s for s in candidate.sources if s in DETAILS_SOURCES), "search")


async def free_copies(providers: Providers, doi: str | None, tried: list[dict[str, str]]) -> list[str]:
    """Where a free copy may be: the repository landing pages Unpaywall lists for `doi`, bar the ones just tried. One
    request, only once a download has failed; the candidate need not carry them, so the app's Add button gets them
    too. A lookup that fails is no copies."""
    http = providers.client("unpaywall")
    if http is None or not doi:
        return []
    try:
        urls = await unpaywall.repository_urls(http, doi)
    except httpx.HTTPError as exc:
        logger.info("no Unpaywall repository copies for %s: %s", doi, redact(str(exc)))
        return []
    seen = {t["url"] for t in tried}
    return [redacted for url in urls if (redacted := redact(url)) not in seen]


ARXIV_SEARCH = "arxiv.org (title search)"
ARXIV_SPACING = 3  # seconds between title searches on one Providers: arXiv asks for no more than one every 3 s
_now = time.monotonic
_sleep = asyncio.sleep  # both patchable, so tests need not wait


async def _space_arxiv_searches(providers: Providers) -> None:
    if providers.last_search and (wait := providers.last_search[0] + ARXIV_SPACING - _now()) > 0:
        await _sleep(wait)
    providers.last_search[:] = [_now()]


UNPAYWALL_LOOKUP = "api.unpaywall.org (DOI lookup)"
_TEMPORARY_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_temporary(outcome: str) -> bool:
    """Whether a `tried` outcome says the source couldn't answer now (rate limited, down, unreachable), not that it has
    no copy: `busy`, `error: <exception>` and these HTTP statuses."""
    if outcome == "busy" or outcome.startswith("error: "):
        return True
    return outcome.startswith("http_") and outcome[5:].isdigit() and int(outcome[5:]) in _TEMPORARY_HTTP


def temporary_failures(tried: list[dict[str, str]]) -> list[dict[str, str]]:
    return [entry for entry in tried if is_temporary(entry["outcome"])]


async def _unpaywall_lookup(providers: Providers, candidate: Candidate) -> tuple[Candidate, list[dict[str, str]]]:
    """Unpaywall's links merged into the candidate, and what the lookup said for `tried`: a download list alone hid
    that it had run, and a busy Unpaywall looked just like a paper with no free copy. Nothing without a DOI."""
    if not candidate.doi:
        return candidate, []
    http = providers.client("unpaywall")
    if http is None:
        return candidate, [{"url": UNPAYWALL_LOOKUP, "outcome": "skipped: off or no contact email"}]
    try:
        urls = await unpaywall.pdf_urls(http, candidate.doi)
    except httpx.HTTPError as exc:
        logger.info("no Unpaywall links for %s: %s", candidate.doi, redact(str(exc)))
        return candidate, [{"url": UNPAYWALL_LOOKUP, "outcome": _search_outcome(exc)}]
    merged = ordered_pdf_urls(candidate.external_ids.get("arxiv"), *candidate.pdf_urls, *urls)
    return replace(candidate, pdf_urls=merged), [
        {"url": UNPAYWALL_LOOKUP, "outcome": "links_found" if urls else "no_copy"}
    ]


def _search_outcome(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return "busy" if code in (429, 503) else f"http_{code}"
    return f"error: {type(exc).__name__}"


def _arxiv_ids(candidate: Candidate) -> list[str]:
    """Every arXiv id the candidate names: its external ids, an arXiv DOI and arXiv links among its PDF URLs."""
    found = [
        candidate.external_ids.get("arxiv"),
        arxiv_from_doi(candidate.doi),
        *(arxiv_from_url(url) for url in candidate.pdf_urls),
    ]
    return list(dict.fromkeys(i for i in found if i))


async def _reuse_arxiv_copy(
    session: AsyncSession,
    candidate: Candidate,
    arxiv_ids: list[str],
    tried: list[dict[str, str]],
    exclude: uuid.UUID | None = None,
) -> None:
    """Raises Conflict(ALREADY_IN_LIBRARY, paper_id, tried) when the library holds one of these arXiv papers (bar
    `exclude`, the paper find_pdf looks for), after recording the candidate's DOI and venue on it as its published
    version, unless another paper holds that DOI as its own (find_pdf's PDF-less paper): the DOI must keep answering
    to that paper alone. Otherwise returns. The transaction ends either way, so no connection idles through the
    downloads that follow.
    ponytail: the lookup keys are the arXiv DOI (`10.48550/arxiv.<id>`) and arXiv links only; a copy filed under
    another DOI is not found."""
    keys = [f"{ARXIV_DOI_PREFIX}{i}".lower() for i in arxiv_ids]
    query = select(Paper).where(func.lower(Paper.doi).in_(keys)).execution_options(populate_existing=True)
    if exclude is not None:
        query = query.where(Paper.id != exclude)
    held = (await session.execute(query)).scalars().first() if keys else None
    if held is not None:
        owner = select(Paper.id).where(func.lower(Paper.doi) == (candidate.doi or "").lower(), Paper.id != held.id)
        if not (candidate.doi and await session.scalar(owner.limit(1))):  # add() never gets here with one: it's held
            apply_published(held, candidate.doi, candidate.venue, details_source(candidate))
    paper_id, asked = held and held.id, held and arxiv_from_doi(held.doi.lower())
    await session.commit()
    if paper_id is not None:
        url = f"https://doi.org/{candidate.doi}" if candidate.doi else f"https://arxiv.org/abs/{asked}"
        raise Conflict(ALREADY_IN_LIBRARY, paper_id=paper_id, tried=[*tried, {"url": url, "outcome": "in_library"}])


async def _reuse_published_copy(session: AsyncSession, candidate: Candidate) -> None:
    """Raises Conflict(ALREADY_IN_LIBRARY, paper_id, tried) when the candidate is an arXiv copy of a paper the library
    already holds as its published version: the same title (or the same title before its colon, when renamed on
    publication) under the arXiv fallback's author and year rules, read with the held paper as the published side.
    The held paper is not changed. Otherwise returns. The transaction ends either way, before any download.
    ponytail: scans the titles that start with the candidate's first word (papers have no title index); it only runs
    for an arXiv copy."""
    is_arxiv_copy = not candidate.doi or arxiv_from_doi(candidate.doi)
    arxiv_id = next(iter(_arxiv_ids(candidate)), None) if is_arxiv_copy else None
    first = next(iter(normal_title(candidate.title).split()), "")
    found = None
    if arxiv_id and first:
        columns = (Paper.id, Paper.title, Paper.authors, Paper.year, Paper.doi, Paper.source_type)
        rows = await session.execute(select(*columns).where(func.lower(Paper.title).startswith(first, autoescape=True)))
        preprint = {"title": candidate.title, "authors": candidate.authors, "year": candidate.year}
        found = next(
            (
                held.id
                for held in rows
                if not is_preprint_copy(held)
                and (published := Candidate(title=held.title, authors=held.authors, year=held.year))
                and (same_work(published, preprint) or _renamed_work(published, preprint))
            ),
            None,
        )
    await session.commit()
    if found is not None:
        tried = [{"url": f"https://arxiv.org/abs/{arxiv_id}", "outcome": "in_library"}]
        raise Conflict(ALREADY_IN_LIBRARY, paper_id=found, tried=tried)


async def held_version(session: AsyncSession, candidate: Candidate) -> tuple[uuid.UUID, bool] | None:
    """The library paper holding the candidate's other version, without downloading anything: its arXiv copy (by arXiv
    id, which then records the candidate as its published version) or its published version (by title, M69).
    Returns (paper id, matched by an identifier) or None. Ends the transaction, as both checks do."""
    try:
        await _reuse_arxiv_copy(session, candidate, _arxiv_ids(candidate), [])
    except Conflict as exc:
        return exc.details["paper_id"], True
    try:
        await _reuse_published_copy(session, candidate)
    except Conflict as exc:
        return exc.details["paper_id"], False
    return None


async def _arxiv_title_copy(
    session: AsyncSession, providers: Providers, candidate: Candidate, tried: list[dict[str, str]]
) -> tuple[bytes | None, list[dict[str, str]]]:
    """Last resort for a paper no source links to arXiv: a title search there, and the PDF of an exact match. A paper
    that may have been renamed on publication gets a second search, by the title before its colon and its first
    author. Returns (the PDF or None, `tried` plus what this step did). Nothing happens when arXiv is off. When the
    library already holds that arXiv paper, it learns the candidate's published version and
    Conflict(ALREADY_IN_LIBRARY, paper_id, tried) is raised instead of downloading."""
    http = providers.client("arxiv")
    if http is None or _has_arxiv_id(candidate):
        return None, tried
    searches = [(candidate.title, None, same_work, "arxiv_title_match")]
    if (prefix := _title_prefix(candidate.title)) and len(candidate.authors) >= 3 and candidate.year:
        searches.append((prefix, surname(candidate.authors[0]), _renamed_work, "arxiv_title_prefix_match"))
    for title, author, same, outcome in searches:
        await _space_arxiv_searches(providers)
        try:
            entries = await arxiv.search(http, title, 5, author)
        except httpx.HTTPError as exc:
            logger.info("no arXiv title search for %s: %s", redact(title), redact(str(exc)))
            return None, [*tried, {"url": ARXIV_SEARCH, "outcome": _search_outcome(exc)}]
        if match := next((e for e in entries if same(candidate, e)), None):
            break
        tried = [*tried, {"url": ARXIV_SEARCH, "outcome": "no_match"}]
    else:
        return None, tried
    arxiv_id = match["arxiv_id"]
    found = [{"url": f"https://arxiv.org/abs/{arxiv_id}", "outcome": outcome}]
    await _reuse_arxiv_copy(session, candidate, [arxiv_id], [*tried, *found])
    data, more = await pdf_download.download_pdf(providers.pdf, ordered_pdf_urls(arxiv_id))
    return data, [*tried, *found, *more]


MAX_DIVA_PDFS = 3
MAX_URN_LOOKUPS = 3
_DIVA_ID = re.compile(r"diva2:(\d+)")


def diva_pdf_url(url: str) -> str | None:
    """The FULLTEXT01.pdf of a DiVA record (any *.diva-portal.org URL naming a diva2:<digits> id), else None."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    found = _DIVA_ID.search(unquote(parts.path + "?" + parts.query))
    if not host.endswith(".diva-portal.org") or parts.scheme not in ("http", "https") or not found:
        return None
    return f"https://{host}/smash/get/diva2:{found.group(1)}/FULLTEXT01.pdf"


async def resolve_kb_urn(http: httpx.AsyncClient, url: str) -> str | None:
    """Where a urn.kb.se link points, when that is a DiVA record: one GET, the redirect not followed."""
    if urlsplit(url).hostname != "urn.kb.se":
        return None
    try:
        response = await http.get(url, follow_redirects=False)
    except (httpx.HTTPError, InvalidInput) as exc:  # InvalidInput: the PDF guard refused the address
        logger.info("urn.kb.se did not resolve %s: %s", redact(url), redact(str(exc)))
        return None
    location = urljoin(url, response.headers.get("location", ""))
    return location if response.is_redirect and diva_pdf_url(location) else None


async def _diva_copy(
    providers: Providers, copies: list[str], tried: list[dict[str, str]]
) -> tuple[bytes | None, list[dict[str, str]]]:
    """The DiVA records among the repository copies (a urn.kb.se link that leads to one too), tried as their
    FULLTEXT PDF: at most MAX_DIVA_PDFS, bar the ones already tried."""
    urls: list[str] = []
    resolved = 0
    for copy in copies:
        pdf = diva_pdf_url(copy)
        if pdf is None and urlsplit(copy).hostname == "urn.kb.se" and resolved < MAX_URN_LOOKUPS:
            resolved += 1
            pdf = diva_pdf_url(await resolve_kb_urn(providers.pdf, copy) or "")
        if pdf and pdf not in urls and pdf not in {t["url"] for t in tried}:
            urls.append(pdf)
        if len(urls) == MAX_DIVA_PDFS:
            break
    if not urls:
        return None, tried
    data, more = await pdf_download.download_pdf(providers.pdf, urls)
    return data, [*tried, *more]


# PMC's own article pages and Europe PMC's, as Unpaywall lists them among a paper's repository copies.
_PMC_LINK = re.compile(
    r"https?://(?:www\.ncbi\.nlm\.nih\.gov/pmc/articles|pmc\.ncbi\.nlm\.nih\.gov/articles"
    r"|(?:www\.)?europepmc\.org/articles?(?:/pmc)?)/(PMC\d+)",
    re.IGNORECASE,
)


def pmcid_of(external_ids: dict, urls: list[str]) -> str | None:
    """The paper's own PMCID (external_ids "pmc", as PMC and Europe PMC store it), else the first PMC article link
    among `urls` ("PMC4512184"), else None."""
    if own := pmc_opendata.normalize(external_ids.get("pmc")):
        return own
    return next((pmc_opendata.normalize(m[1]) for url in urls if (m := _PMC_LINK.match(url))), None)


async def pmc_copy(
    providers: Providers, external_ids: dict, doi: str | None, copies: list[str], tried: list[dict[str, str]]
) -> tuple[bytes | None, list[dict[str, str]]]:
    """NCBI's PMC Open Access bucket (M76), for a paper with a PMCID: its own, a PMC link among its free copies, or
    the one Europe PMC gives for its DOI (only when that source is on). Nothing is asked without a PMCID."""
    # A PMC page already tried (a bot-checked europepmc ?pdf=render, say) still names the PMCID.
    pmcid = pmcid_of(external_ids, [*copies, *(t["url"] for t in tried)])
    if pmcid is None and doi and (epmc := providers.client("europe_pmc")) is not None:
        try:
            pmcid = pmc_opendata.normalize(await europe_pmc.pmcid_for_doi(epmc, doi))
        except httpx.HTTPError as exc:
            logger.info("no PMCID from Europe PMC for %s: %s", doi, redact(str(exc)))
    if pmcid is None:
        return None, tried
    try:
        url, listed = await pmc_opendata.pdf_url(providers.pdf, pmcid)
    except InvalidInput as exc:  # the PDF client's guard: the bucket's host didn't resolve to a public address
        if str(exc) != "unsafe_url":
            raise
        return None, [*tried, {"url": pmc_opendata.listing_url(pmcid), "outcome": "unsafe_url"}]
    except httpx.HTTPError as exc:
        outcome = f"http_{exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else (
            f"error: {type(exc).__name__}"
        )  # fmt: skip
        return None, [*tried, {"url": pmc_opendata.listing_url(pmcid), "outcome": outcome}]
    if url is None:
        return None, [*tried, {"url": listed, "outcome": "no_match"}]
    await pmc_opendata.wait_turn()
    data, more = await pdf_download.download_pdf(providers.pdf, [url])
    return data, [*tried, *more]


async def _download_free_copy(
    session: AsyncSession, providers: Providers, candidate: Candidate, lookups: list[dict[str, str]] | None = None
) -> tuple[bytes | None, list[dict[str, str]], list[str]]:
    """The download waterfall add() and find_pdf() share: the candidate's PDF URLs, the arXiv title copy, DiVA among
    the repository copies, then PMC. (the PDF or None, the lookups and what each URL tried said, the repository
    copies)."""
    data, downloads = await pdf_download.download_pdf(providers.pdf, candidate.pdf_urls)
    tried = [*(lookups or []), *downloads]
    copies: list[str] = []
    if data is None:
        data, tried = await _arxiv_title_copy(session, providers, candidate, tried)
    if data is None:
        copies = await free_copies(providers, candidate.doi, tried)
        data, tried = await _diva_copy(providers, copies, tried)
    if data is None:
        data, tried = await pmc_copy(providers, candidate.external_ids, candidate.doi, copies, tried)
    return data, tried, copies


async def find_pdf(
    session: AsyncSession, providers: Providers, candidate: Candidate
) -> tuple[bytes | None, list[dict[str, str]], list[str]]:
    """A free copy for a paper the library holds without one (R11): Unpaywall's links merged in, then add()'s
    waterfall. Returns (the PDF or None, what each URL tried said, the repository pages that may hold a copy); stores
    nothing. add()'s check for a held published version is left out (it decides whether to create a paper); a held
    arXiv copy of the same work, named by the candidate (bar `candidate.paper_id`, the paper itself) or found by the
    title search, raises Conflict(ALREADY_IN_LIBRARY, paper_id, tried): a duplicate rather than a second file, and
    nothing is recorded on it. Ends the transaction first, so no connection idles through the downloads."""
    await session.commit()
    candidate, lookups = await _unpaywall_lookup(providers, candidate)
    # An arXiv paper it names that the library holds is the same duplicate as the title search's: no second copy.
    await _reuse_arxiv_copy(session, candidate, _arxiv_ids(candidate), [], exclude=candidate.paper_id)
    return await _download_free_copy(session, providers, candidate, lookups)
