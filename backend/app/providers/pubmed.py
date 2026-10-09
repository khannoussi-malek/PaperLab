"""PubMed (NCBI E-utilities) over HTTP. Network failures, timeouts and error statuses (429 included) raise
httpx.HTTPError.

Probed live on 2026-10-09: search is a two-step dance — `esearch.fcgi` answers with PMIDs only (no title,
no abstract), and the actual record comes from a separate `efetch.fcgi?retmode=xml` call, which accepts a
comma-separated `id` list to fetch several records in one request. `efetch`'s own `retmode=json` is a trap:
it answers HTTP 200 with `content-type: application/json`, but the body is just the bare PMID as plain
text, not a structured record — XML is the only mode that actually returns the article. An unknown PMID
answers HTTP 200 with an empty `<PubmedArticleSet></PubmedArticleSet>`, never a 404. PubMed's own XML has no
namespace (plain `<PMID>`, `<ArticleTitle>`, unlike arXiv's Atom feed). Rate limit: 3 requests/second
without a key, 10/second with NCBI's own free API key.
"""

import xml.etree.ElementTree as ET

import httpx

from app.providers.http import RateLimited
from app.providers.openalex import json_body

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = httpx.Timeout(10.0)
# NCBI's own documented ceiling: 3 req/s unauthenticated, 10 req/s with a free API key.
_MIN_INTERVAL_NO_KEY = 1 / 3
_MIN_INTERVAL_WITH_KEY = 1 / 10


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # NCBI asks every caller to identify itself with tool/email (its own usage policy); api_key rides in the
    # query string, same as NCBI's own documented usage (unlike OpenAlex's key-in-header convention).
    params = {k: v for k, v in {"tool": "paperlab", "email": email, "api_key": api_key}.items() if v}
    min_interval = _MIN_INTERVAL_WITH_KEY if api_key else _MIN_INTERVAL_NO_KEY
    limited = RateLimited(transport or httpx.AsyncHTTPTransport(), min_interval)
    return httpx.AsyncClient(base_url=BASE_URL, params=params, timeout=TIMEOUT, transport=limited)


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL (which carries the
    NCBI api_key query param) — that message ends up in cursor.last_error and worker logs."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"PubMed answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


async def _esearch(http: httpx.AsyncClient, term: str, limit: int, start: int) -> tuple[list[str], int]:
    """PMIDs matching `term` (at most `limit`, from `start`), and NCBI's own total count for the query."""
    response = await http.get(
        "/esearch.fcgi",
        params={
            "db": "pubmed", "term": term, "retmax": limit, "retstart": start, "retmode": "json",
            "sort": "relevance",
        },
    )
    result = json_body(_checked(response))["esearchresult"]
    if "ERROR" in result:
        # Documented NCBI behavior: HTTP 200 with no idlist/count on a malformed query, an empty term, or
        # retstart past the 9,999-record ceiling. Raising an httpx.HTTPError here (not letting the bare
        # KeyError escape) is what lets discovery.search/workspace_search.search_batch treat this source
        # as "failed for this request", same as any other provider error, instead of crashing the whole run.
        raise httpx.DecodingError(result["ERROR"], request=response.request)
    return result["idlist"], int(result["count"])


async def _efetch(http: httpx.AsyncClient, pmids: list[str]) -> list[dict]:
    """The full records for `pmids`, one batched request. `pmids` must be non-empty — callers check first,
    so a term with zero matches never spends a second request fetching nothing."""
    response = await http.get("/efetch.fcgi", params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
    return _entries(_checked(response))


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    ids, _ = await _esearch(http, term, limit, start=0)
    return await _efetch(http, ids) if ids else []


async def get(http: httpx.AsyncClient, pmid: str) -> dict | None:
    """One paper by PMID, or None when PubMed has no such record."""
    entries = await _efetch(http, [pmid])
    return entries[0] if entries else None


async def search_page(http: httpx.AsyncClient, term: str, page_size: int, cursor: int) -> tuple[list[dict], int | None]:
    """One page of PubMed results. `cursor` is `retstart`; returns (entries, next_start_or_None), using
    NCBI's own reported total (`count`) to decide whether there is more — a more reliable signal than
    whether this page happened to be full-sized."""
    ids, count = await _esearch(http, term, page_size, start=cursor)
    entries = await _efetch(http, ids) if ids else []
    # ponytail: NCBI's ESearch hard ceiling (retstart can't exceed 9998); usehistory=y would lift it, not
    # needed yet since no run has hit this in practice.
    next_cursor = cursor + page_size if cursor + page_size < min(count, 9999) else None
    return entries, next_cursor


def _entries(response: httpx.Response) -> list[dict]:
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise httpx.DecodingError(str(exc), request=response.request) from exc
    if root.tag != "PubmedArticleSet":
        raise httpx.DecodingError("PubMed's answer is not a PubmedArticleSet", request=response.request)
    return [entry for node in root.findall("PubmedArticle") if (entry := _entry(node))]


def _text(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _entry(node: ET.Element) -> dict | None:
    pmid = node.findtext("MedlineCitation/PMID")
    article = node.find("MedlineCitation/Article")
    if not pmid or article is None:
        return None
    doi = next((el.text for el in article.findall("ELocationID") if el.get("EIdType") == "doi"), None)
    if not doi:
        # Fall back to PubmedData's own ArticleIdList (a sibling of MedlineCitation, read from `node` not
        # `article` so this never picks up a ReferenceList's own, unrelated ArticleIdList entries) — most
        # older records carry their DOI only here, not in ELocationID.
        doi = node.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='doi']")
    year = article.findtext("Journal/JournalIssue/PubDate/Year")
    authors = [
        joined
        for author in article.findall("AuthorList/Author")
        if (joined := " ".join(filter(None, (author.findtext("ForeName"), author.findtext("LastName")))))
    ]
    abstract_parts = [text for el in article.findall("Abstract/AbstractText") if (text := _text(el))]
    title_el = article.find("ArticleTitle")
    return {
        "pmid": pmid,
        "title": _text(title_el) if title_el is not None else "",
        "authors": authors,
        "year": int(year) if year and year.isdigit() else None,
        "doi": doi.strip().lower() if doi else None,
        "abstract": " ".join(abstract_parts).strip() or None,
    }
