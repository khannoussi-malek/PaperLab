"""Europe PMC's REST API (https://www.ebi.ac.uk/europepmc/webservices/rest). No key required. Network
failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed live on 2026-10-09: one-step search (GET /search?query=...&resultType=core), unlike PubMed/PMC's
esearch-then-efetch dance -- resultType=core returns title, authors, abstractText, doi, pmid, pmcid and
citedByCount all in the one response. Default sort is also newest-first, the same trap PubMed/PMC have
(confirmed live: "attention is all you need" without sort=relevance returns unrelated recent papers
first) -- sort=relevance is requested explicitly. cursorMark pagination is count-aware, not
page-fullness-based: nextCursorMark is present in the response if and only if there is a next page
(confirmed live at an exact page/hitCount boundary: pageSize=1 with hitCount=1 omits it even though the
page is "full") -- search_page just checks for that key, no retstart-style arithmetic needed. A `page=N`
parameter exists in the response echo but is silently ignored by the server (confirmed: requesting
page=2 returns page 1's own ids) -- cursorMark is the only pagination mechanism this endpoint honors, and
it is an OPAQUE STRING TOKEN, never a number (e.g. "AoIIQc79gCg1NjU1MDU5Ng=="); passing a plain integer
as a cursorMark is rejected. An empty or missing query answers a real HTTP 404 (not NCBI's
200-with-ERROR-key quirk), so the ordinary raise_for_status() path already handles it -- no
special-casing needed, unlike pubmed.py/pmc.py.

Two probed data-quality notes, not bugs to work around, just real API behavior mapped through as-is:
(1) title/abstractText can themselves contain inline HTML-ish markup as literal text (e.g. "the <i>in
vivo</i> delivery") -- stripped with a small regex, since these are plain JSON string values, not real
XML elements (itertext() doesn't apply here). (2) a record Europe PMC indexes under source="PMC" (as
opposed to "MED") can have pmid/doi/abstractText as null even when PMC's own feed has them (a real
cross-linking lag in Europe PMC's own pipeline, confirmed by comparing the same article's PMC-sourced and
MEDLINE-sourced Europe PMC records against that article's own direct PMC efetch record) -- handled by
the same plain dict.get(...) every other optional field already needs, not a defect.

Every identifier this module reports (pmid, pmcid) reuses the SAME external_ids keys PubMed/PMC already
own ("pubmed", "pmc") rather than inventing a third "europe_pmc" id kind -- see candidates.py's
from_europe_pmc for why.

The website's own direct PDF link (a fullTextUrlList entry with documentStyle="pdf", e.g.
https://europepmc.org/articles/PMC.../?pdf=render) answers HTTP 403 behind a Cloudflare bot challenge on
every probe (confirmed with and without a browser User-Agent) -- this module never reports a PDF link,
same scope decision as ACM DL/SSRN (metadata/abstract only, never a promised PDF that mostly won't load).
EBI publishes no documented rate limit for this endpoint; this stays as polite as every other keyless
source in this codebase (ponytail: raise the pace if a real throttle response is ever seen).
"""

import re

import httpx

from app.providers.http import RateLimited

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
TIMEOUT = httpx.Timeout(10.0)
_MIN_INTERVAL = 1 / 3

_TAG = re.compile(r"<[^>]+>")


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # Europe PMC takes neither a contact email nor an API key; both parameters exist only to satisfy the
    # uniform new_client(*, email=None, api_key=None, transport=None) signature every provider shares.
    limited = RateLimited(transport or httpx.AsyncHTTPTransport(), _MIN_INTERVAL)
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=limited)


def _clean(text: str | None) -> str:
    return " ".join(_TAG.sub("", text or "").split())


def _json_body(response: httpx.Response) -> dict:
    try:
        return response.json()
    except ValueError as exc:
        raise httpx.DecodingError(str(exc), request=response.request) from exc


async def _search(http: httpx.AsyncClient, term: str, page_size: int, cursor_mark: str) -> httpx.Response:
    return await http.get(
        "/search",
        params={
            "query": term, "format": "json", "resultType": "core", "pageSize": page_size,
            "cursorMark": cursor_mark, "sort": "relevance",
        },
    )


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    response = await _search(http, term, limit, "*")
    body = _json_body(response.raise_for_status())
    return [_entry(r) for r in body["resultList"]["result"]]


async def get(http: httpx.AsyncClient, ext_id: str) -> dict | None:
    """One paper by a PMID or bare PMC id (Europe PMC's own EXT_ID query field matches either), or None
    when Europe PMC has no such record."""
    entries = await search(http, f"EXT_ID:{ext_id}", 1)
    return entries[0] if entries else None


async def search_page(
    http: httpx.AsyncClient, term: str, page_size: int, cursor: str
) -> tuple[list[dict], str | None]:
    """`cursor` is a cursorMark string, opaque to callers ("*" starts from the first page -- the
    registry's own starting_cursor="*" for this source seeds every fresh run with it). Returns
    (entries, next_cursor_or_None): Europe PMC says directly whether there's a next page by whether
    nextCursorMark is present at all, so there's no count/page-size arithmetic to get wrong."""
    response = await _search(http, term, page_size, cursor)
    body = _json_body(response.raise_for_status())
    entries = [_entry(r) for r in body["resultList"]["result"]]
    return entries, body.get("nextCursorMark")


def _entry(raw: dict) -> dict:
    authors = [a["fullName"] for a in raw.get("authorList", {}).get("author", []) if a.get("fullName")]
    year = raw.get("pubYear")
    pmcid = raw.get("pmcid")
    return {
        "pmid": raw.get("pmid") or None,
        "pmcid": pmcid.removeprefix("PMC") if pmcid else None,
        "title": _clean(raw.get("title")),
        "authors": authors,
        "year": int(year) if year and year.isdigit() else None,
        "doi": raw["doi"].strip().lower() if raw.get("doi") else None,
        "abstract": _clean(raw.get("abstractText")) or None,
        "cited_by_count": raw.get("citedByCount"),
    }
