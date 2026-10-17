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
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import paper_sources, papers, pdf_links, source_registry
from app.core.candidates import (
    ARXIV_ID,
    Candidate,
    arxiv_from_doi,
    arxiv_from_url,
    from_s2,
    merge,
    normal_title,
    ordered_pdf_urls,
    surname,
    with_s2,
)
from app.core.enrichment import ARXIV_DOI_PREFIX
from app.core.errors import Conflict, InvalidInput
from app.core.paper_enrichment import apply_published
from app.core.paper_sources import KEYED, NAMES, SourceSettings
from app.core.redact import redact
from app.core.source_registry import ASKS
from app.core.source_types import is_preprint_copy
from app.models import Paper
from app.providers import arxiv, discovery_fake, semantic_scholar, unpaywall

logger = logging.getLogger(__name__)

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
    """The clients one request uses. A source that is off, or lacks a key it needs, has none in `clients`; a PDF
    host (arxiv.org, a publisher, a repository, or a redirect target) never agreed to receive the owner's email,
    so `pdf` is separate and always present."""

    pdf: httpx.AsyncClient
    clients: dict[str, httpx.AsyncClient] = field(default_factory=dict)
    # When this Providers last searched arXiv by title (one slot, mutated): a bulk add spaces its searches by it.
    last_search: list[float] = field(default_factory=list, compare=False)

    def client(self, source: str) -> httpx.AsyncClient | None:
        return self.clients.get(source)

    def without(self, *sources: str) -> "Providers":
        """A copy with these sources' clients removed — for tests simulating a source being off."""
        return replace(self, clients={k: v for k, v in self.clients.items() if k not in sources})

    async def aclose(self) -> None:
        await self.pdf.aclose()
        for client in self.clients.values():
            await client.aclose()


@dataclass(frozen=True)
class SearchResult:
    results: list[Candidate]
    notices: list[str]  # one per source that failed


def build_providers(sources: SourceSettings, transport: httpx.AsyncBaseTransport | None = None) -> Providers:
    on, email, keys = sources.enabled, sources.contact_email, sources.api_keys
    clients = {
        spec.id: spec.new_client(email=email, api_key=keys.get(spec.key_source or spec.id), transport=transport)
        for spec in source_registry.REGISTRY
        if (sources.unpaywall_on if spec.id == "unpaywall" else on[spec.id])
    }
    return Providers(
        # No email: unlike the sources, a PDF host (arxiv.org, a publisher, a repository, or a redirect target) never
        # agreed to receive the owner's email.
        pdf=httpx.AsyncClient(
            timeout=PDF_TIMEOUT, follow_redirects=True, headers={"User-Agent": PDF_USER_AGENT}, transport=transport,
            event_hooks={"request": [pdf_links.guard]},  # every hop, redirects included
        ),
        clients=clients,
    )


@asynccontextmanager
async def open_providers(session: AsyncSession) -> AsyncIterator[Providers]:
    """The clients for one request or tool call, from Settings → Paper sources, closed after it. With
    DISCOVERY_PROVIDER=fake every source answers offline (E2E)."""
    sources = await paper_sources.get(session)
    transport = None
    if settings.discovery_provider == "fake":
        transport = discovery_fake.transport()
        # The fake answers Unpaywall offline, so its placeholder can stand in for the email Unpaywall needs.
        sources = replace(sources, contact_email=sources.contact_email or discovery_fake.MAILTO)
    providers = build_providers(sources, transport)
    if transport is not None:
        providers.pdf.event_hooks["request"].clear()  # the fake's hosts never resolve, and nothing leaves the process
    try:
        yield providers
    finally:
        await providers.aclose()


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


BOT_CHECK_STATUSES = (403, 429, 503)
CHALLENGE_MARKERS = (b"Just a moment", b"challenge-platform")


async def _is_bot_check(response: httpx.Response) -> bool:
    """A Cloudflare challenge: its `cf-mitigated` header, or its interstitial page. Recognised, never answered."""
    if response.status_code not in BOT_CHECK_STATUSES:
        return False
    if "cf-mitigated" in response.headers:
        return True
    if "cloudflare" not in response.headers.get("server", "").lower():
        return False
    async for chunk in response.aiter_bytes():  # the first chunk holds the page's title
        return any(marker in chunk for marker in CHALLENGE_MARKERS)
    return False


MAX_LANDING_BYTES = 2 * 1024 * 1024
PDF_USER_AGENT = "PaperLab (+https://github.com/khannoussi-malek/PaperLab)"  # names the tool; never imitates a browser
FOLLOWED = "not_a_pdf → followed citation_pdf_url"


class _PdfMeta(HTMLParser):
    """The first `<meta name="citation_pdf_url" content=…>`, its attributes in either order."""

    def __init__(self):
        super().__init__()
        self.url: str | None = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if self.url is None and tag == "meta" and (fields.get("name") or "").lower() == "citation_pdf_url":
            self.url = (fields.get("content") or "").strip() or None


def _declared_pdf(page: str, base: str) -> str | None:
    parser = _PdfMeta()
    parser.feed(page)
    return urljoin(base, parser.url) if parser.url else None


async def _fetch_pdf(http: httpx.AsyncClient, url: str) -> tuple[bytes | None, str, str | None]:
    """(the PDF or None, why, the page's declared PDF URL or None): why is `pdf`, `http_<status>`, `bot_check`,
    `too_large` or `not_a_pdf`. Only a not_a_pdf page under MAX_LANDING_BYTES can declare a PDF."""
    async with http.stream("GET", url) as response:
        if response.status_code != 200:
            outcome = "bot_check" if await _is_bot_check(response) else f"http_{response.status_code}"
            logger.info("no PDF at %s: %s", redact(url), outcome)
            return None, outcome, None
        final_url = str(response.url)
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) > MAX_PDF_BYTES:
                logger.info("no PDF at %s: over %d bytes", redact(url), MAX_PDF_BYTES)
                return None, "too_large", None
    if not body.startswith(papers.PDF_MAGIC):
        logger.info("no PDF at %s: the body is not a PDF", redact(url))
        declared = None
        if len(body) < MAX_LANDING_BYTES:
            declared = _declared_pdf(body.decode("utf-8", errors="replace"), final_url)
        return None, "not_a_pdf", declared
    return bytes(body), "pdf", None


async def _try(http: httpx.AsyncClient, url: str, check: bool = False) -> tuple[bytes | None, str, str | None]:
    try:
        if check:  # a URL a publisher page declared is not the caller's own link: never fetch a private address
            await pdf_links.check_url(url)
        return await _fetch_pdf(http, url)
    except InvalidInput as exc:
        if str(exc) != "unsafe_url":
            raise
        return None, "unsafe_url", None
    except httpx.HTTPError as exc:
        logger.info("no PDF at %s: %s", redact(url), redact(str(exc)))
        return None, f"error: {type(exc).__name__}", None


async def download_pdf(http: httpx.AsyncClient, urls: list[str]) -> tuple[bytes | None, list[dict[str, str]]]:
    """(the first body that is a PDF, what each URL tried said), in order. A failing URL moves on to the next; a page
    that declares its PDF (citation_pdf_url) gets that one URL tried too, and a followed page is not followed again.
    The URLs in `tried` have their query secrets hidden."""
    tried: list[dict[str, str]] = []
    for url in urls:
        data, outcome, declared = await _try(http, url)
        tried.append({"url": redact(url), "outcome": FOLLOWED if declared else outcome})
        if declared:
            # ponytail: one hop; the PDF's own page is not followed
            data, outcome, _ = await _try(http, declared, check=True)
            tried.append({"url": redact(declared), "outcome": outcome})
        if data is not None:
            return data, tried
    return None, tried


def prefill(candidate: Candidate) -> dict[str, Any]:
    """Enrichment trusts a stored openalex_id, and a DOI only when it's locked (D69). The title is always locked:
    ingest's PDF-font heuristic and enrichment's metadata are both worse than the title the source already gave us,
    so it must survive both (M7.5)."""
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
    return fields | {"manual_fields": locked}


def _filename(title: str) -> str:
    return f"{re.sub(r'[^\w\- ]+', '', title).strip()[:80] or 'paper'}.pdf"


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


_PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "dos", "du", "la", "le", "ter", "bin"}


def _surname_forms(name: str) -> set[str]:
    """The ways a surname may be written: its last token ("berg") and with its particles ("van der berg")."""
    last = surname(name)
    if "," in name:
        return {last.split()[-1], last} if last else set()
    tokens = [surname(token) for token in name.split()]
    start = len(tokens) - 1
    while start > 0 and tokens[start - 1] in _PARTICLES:
        start -= 1
    return {tokens[-1], " ".join(tokens[start:])} if tokens else set()


def _same_work(candidate: Candidate, entry: dict) -> bool:
    """An arXiv entry is the candidate's preprint: the same title word for word; the same first author or at least
    two shared surnames (with no authors on either side, a year within one); and not posted more than a year after
    the paper. A wrong match would ingest another paper, so this is strict."""
    if normal_title(entry["title"]) != normal_title(candidate.title):
        return False
    if None not in (candidate.year, entry["year"]) and entry["year"] > candidate.year + 1:
        return False
    ours, theirs = candidate.authors, entry["authors"]
    if not ours and not theirs:
        return None not in (candidate.year, entry["year"]) and abs(candidate.year - entry["year"]) <= 1
    if not ours or not theirs:
        return False
    their_forms = [_surname_forms(name) for name in theirs]
    if _surname_forms(ours[0]) & their_forms[0]:
        return True
    return sum(any(_surname_forms(name) & forms for forms in their_forms) for name in ours) >= 2


def _title_prefix(title: str) -> str | None:
    """The normalised text before a title's first colon ("real sampling"), when there is one of two words or more."""
    head, colon, _ = title.partition(":")
    # Words split on spaces, so "GPT-4" or "Self-RAG" stays one name, too short to identify a paper.
    return normal_title(head) if colon and len(head.split()) >= 2 else None


_SERIES_PART = re.compile(r"\b(?:part|vol(?:ume)?)\s+(?:[ivx]+|\d+)\b", re.IGNORECASE)


def _initial(name: str) -> str:
    """The first given-name initial, ASCII-folded ("Chang, Haw-Shiuan" and "Haw-Shiuan Chang" give "h"), or ""."""
    given = name.split(",", 1)[1] if "," in name else " ".join(name.split()[:-1])
    return surname(next(iter(given.split()), ""))[:1]


def _same_author(ours: str, theirs: str) -> bool:
    initials = {_initial(ours), _initial(theirs)}
    return bool(_surname_forms(ours) & _surname_forms(theirs)) and ("" in initials or len(initials) == 1)


def _renamed_work(candidate: Candidate, entry: dict) -> bool:
    """An arXiv entry is the preprint of a paper renamed on publication: the same text before the colon (two words or
    more), the same three or more authors in the same order (surname and first initial), the paper published 0 to 2
    years after the preprint, and neither title a part of a series ("Part II"), whose parts share a prefix and authors.
    The title test is looser than _same_work's, so the author and year tests are stricter."""
    ours, theirs = candidate.authors, entry["authors"]
    return (
        (prefix := _title_prefix(candidate.title)) is not None
        and prefix == _title_prefix(entry["title"])
        and not any(_SERIES_PART.search(t) for t in (candidate.title, entry["title"]))
        and len(ours) >= 3
        and len(ours) == len(theirs)
        and all(_same_author(a, b) for a, b in zip(ours, theirs))
        and None not in (candidate.year, entry["year"])
        and entry["year"] <= candidate.year <= entry["year"] + 2
    )


def _has_arxiv_id(candidate: Candidate) -> bool:
    return bool(
        candidate.external_ids.get("arxiv")
        or arxiv_from_doi(candidate.doi)
        or any("arxiv.org/" in url for url in candidate.pdf_urls)
    )


ARXIV_SEARCH = "arxiv.org (title search)"
ARXIV_SPACING = 3  # seconds between title searches on one Providers: arXiv asks for no more than one every 3 s
_now = time.monotonic
_sleep = asyncio.sleep  # both patchable, so tests need not wait


async def _space_arxiv_searches(providers: Providers) -> None:
    if providers.last_search and (wait := providers.last_search[0] + ARXIV_SPACING - _now()) > 0:
        await _sleep(wait)
    providers.last_search[:] = [_now()]


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
    session: AsyncSession, candidate: Candidate, arxiv_ids: list[str], tried: list[dict[str, str]]
) -> None:
    """Raises Conflict(ALREADY_IN_LIBRARY, paper_id, tried) when the library holds one of these arXiv papers, after
    recording the candidate's DOI and venue on it as its published version. Otherwise returns. The transaction ends
    either way, so no connection idles through the downloads that follow.
    ponytail: the lookup keys are the arXiv DOI (`10.48550/arxiv.<id>`) and arXiv links only; a copy filed under
    another DOI is not found."""
    keys = [f"{ARXIV_DOI_PREFIX}{i}".lower() for i in arxiv_ids]
    query = select(Paper).where(func.lower(Paper.doi).in_(keys)).execution_options(populate_existing=True)
    held = (await session.execute(query)).scalars().first() if keys else None
    if held is not None:
        apply_published(held, candidate.doi, candidate.venue)
    paper_id = held and held.id
    await session.commit()
    if paper_id is not None:
        found = {"url": f"https://doi.org/{candidate.doi}", "outcome": "in_library"}
        raise Conflict(ALREADY_IN_LIBRARY, paper_id=paper_id, tried=[*tried, found])


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
                and (_same_work(published, preprint) or _renamed_work(published, preprint))
            ),
            None,
        )
    await session.commit()
    if found is not None:
        tried = [{"url": f"https://arxiv.org/abs/{arxiv_id}", "outcome": "in_library"}]
        raise Conflict(ALREADY_IN_LIBRARY, paper_id=found, tried=tried)


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
    searches = [(candidate.title, None, _same_work, "arxiv_title_match")]
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
    data, more = await download_pdf(providers.pdf, ordered_pdf_urls(arxiv_id))
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
    data, more = await download_pdf(providers.pdf, urls)
    return data, [*tried, *more]


async def add(
    session: AsyncSession, providers: Providers, candidate: Candidate, pdf_dir: Path, tried_out: list | None = None
) -> Paper:
    """Downloads the candidate's first free PDF and creates the paper. The caller enqueues ingest. A caller that
    wants to know what each URL said passes `tried_out` (a failure carries it on the Conflict anyway)."""
    [marked] = await mark_in_library(session, [candidate])
    if marked.paper_id is not None:
        raise Conflict(ALREADY_IN_LIBRARY, paper_id=marked.paper_id)
    # Release the connection (and its transaction) before a download that can take up to several 30s reads.
    await session.commit()
    await _reuse_published_copy(session, candidate)  # the reverse: its published version is held
    if candidate.doi and candidate.pdf_urls:  # one extra request: a repository copy beside a bot-checked publisher
        [candidate] = await _add_unpaywall_links(providers.client("unpaywall"), [candidate], merge=True)
    await _reuse_arxiv_copy(session, candidate, _arxiv_ids(candidate), [])  # before any download
    data, tried = await download_pdf(providers.pdf, candidate.pdf_urls)
    copies: list[str] = []
    if data is None:
        data, tried = await _arxiv_title_copy(session, providers, candidate, tried)
    if data is None:
        copies = await free_copies(providers, candidate.doi, tried)
        data, tried = await _diva_copy(providers, copies, tried)
    if tried_out is not None:
        tried_out.extend(tried)
    if data is None:
        raise Conflict(NO_FREE_PDF, tried=tried, free_copies=copies)
    # ponytail: two adds of one paper racing past the check above hit papers' UNIQUE doi and 500. The buttons disable
    # while adding; catch IntegrityError here if it ever happens.
    return await papers.create_paper(session, _filename(candidate.title), data, pdf_dir, prefill=prefill(candidate))
