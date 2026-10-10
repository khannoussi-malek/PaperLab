"""OpenAIRE Graph API (https://api.openaire.eu/graph/v3/research-products). Network failures, timeouts
and error statuses (429 included) raise httpx.HTTPError.

Probed live on 2026-10-10: the real, working path is hyphenated -- /graph/v3/research-products, NOT
/v3/researchProducts (confirmed live: the camelCase form answers a 405 "No static resource"). No
Authorization header is required for basic search (confirmed live: a plain anonymous request got a real
200 with its own x-ratelimit-limit: 7199 response header -- this codebase builds no OAuth2 token-refresh
machinery for the documented higher tier, since anonymous access already approximates it in practice;
api_key/email exist only to satisfy the uniform new_client signature every provider shares and are never
used). type=publication correctly filters out non-paper content (confirmed live: an unfiltered query's
own results include type: "software" entries with null authors/descriptions/pids) -- every request here
sends this filter. Pagination is page/pageSize with a reported numFound, 1-based (confirmed live), the
same shape openalex.py's own search_page already uses. An absurdly large pageSize answers a real HTTP
400 (confirmed live: 999999 -- unlike DOAJ's own silent-clamp convention). An unknown id answers a clean
HTTP 404 (confirmed live). instances[].urls are DOI-resolver landing-page links, confirmed NOT direct
PDFs in a live sample -- no PDF is ever attempted from this source, matching crossref.py's own
established "no PDF, links are for identification only" precedent.
"""

import httpx

from app.providers.openalex import json_body

BASE_URL = "https://api.openaire.eu/graph/v3"
TIMEOUT = httpx.Timeout(10.0)
MAX_RESULTS = 10000  # OpenAIRE's own hard ceiling (confirmed live: page=501 at pageSize=20 answers a
# real HTTP 400, "Page * pageSize must be less than or equal to 10000") -- search_page stops signaling
# "more" once a page would cross this line, instead of letting a broad query eventually hit the 400.


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # OpenAIRE's higher tier needs an hourly-refreshing OAuth2 token, a mechanism this codebase has no
    # machinery for; anonymous access already approximates it in practice (confirmed live). api_key/email
    # exist only to satisfy the uniform new_client(*, email=None, api_key=None, transport=None) signature
    # every provider shares and are never used (ponytail: wire a real token-refresh flow if a later
    # milestone needs OpenAIRE's documented higher tier badly enough to justify building one).
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=transport)


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL -- same convention
    every provider in this codebase follows."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"OpenAIRE answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


async def _search(http: httpx.AsyncClient, term: str, page_size: int, page: int) -> httpx.Response:
    params = {"search": term, "type": "publication", "pageSize": page_size, "page": page}
    return await http.get("/research-products", params=params)


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    response = await _search(http, term, limit, 1)
    body = json_body(_checked(response))
    return body["results"]


async def get(http: httpx.AsyncClient, record_id: str) -> dict | None:
    """One research product by its OpenAIRE id, or None when OpenAIRE has no such record."""
    response = await http.get(f"/research-products/{record_id}")
    if response.status_code == 404:
        return None
    return json_body(_checked(response))


async def search_page(
    http: httpx.AsyncClient, term: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    """`cursor` is a 1-based page number (OpenAIRE's own convention; the registry seeds it at 1 via
    starting_cursor) -- the same shape openalex.py's own search_page already uses. Returns (entries,
    next_page_or_None); "is there more" is cursor * page_size < the response's own reported numFound."""
    response = await _search(http, term, page_size, cursor)
    body = json_body(_checked(response))
    next_cursor = cursor + 1 if cursor * page_size < min(body["header"]["numFound"], MAX_RESULTS) else None
    return body["results"], next_cursor
