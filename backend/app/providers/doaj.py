"""DOAJ (https://doaj.org/api/search/articles/). Network failures, timeouts and error statuses (429
included) raise httpx.HTTPError.

Probed live on 2026-10-10: one-step search, query syntax is Elasticsearch-style, URL-encoded directly
into the path (not a query param) -- "title:\"machine learning\"" works once percent-encoded, including
with a colon or slash inside the quoted phrase (confirmed live: no HAL-style body-level trap here).
`pageSize` is silently clamped to 100 when a larger value is requested (confirmed live: 101 and 200 both
answer HTTP 200 with the body itself reporting pageSize: 100) -- not rejected. The response carries a
"next" key (a full URL) exactly when more pages exist, omitted on the last page -- the same
presence/absence pagination signal Zenodo's own search_page already uses in this codebase. Rate limit
confirmed verbatim from DOAJ's own /api/docs page: 2 requests/second, bursts of up to 5 queued -- no key
raises this (a key only raises write limits, confirmed from the same page), so this module never sends
one. An invalid sort value answers a real HTTP 400 (no trap). A single-article lookup on an unknown id
answers a clean HTTP 404 (confirmed live), not a silent empty set.
"""

from urllib.parse import quote

import httpx

from app.providers.openalex import json_body

BASE_URL = "https://doaj.org/api"
TIMEOUT = httpx.Timeout(10.0)
MAX_PAGE_SIZE = 100  # DOAJ's own silent cap (confirmed live) -- this module always requests at most 100.
MAX_RESULTS = 1000  # DOAJ's own hard ceiling (confirmed live: page 11 at pageSize=100 answers a real
# HTTP 400, "You cannot access results beyond 1000 records via this API") -- search_page stops signaling
# "more" once a page would cross this line, instead of letting a broad query eventually hit the 400.


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # DOAJ takes neither a contact email nor a search-relevant key; both parameters exist only to satisfy
    # the uniform new_client(*, email=None, api_key=None, transport=None) signature every provider shares.
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=transport)


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL -- same convention
    every provider in this codebase follows."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"DOAJ answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


def _query(term: str) -> str:
    # DOAJ's query syntax is Elasticsearch-style: a phrase with whitespace needs quoting to search as one
    # unit, a single word doesn't (confirmed live).
    return f'title:"{term}"' if " " in term else f"title:{term}"


async def _search(http: httpx.AsyncClient, term: str, page_size: int, page: int) -> httpx.Response:
    path = f"/search/articles/{quote(_query(term), safe='')}"
    return await http.get(path, params={"page": page, "pageSize": page_size})


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    response = await _search(http, term, min(limit, MAX_PAGE_SIZE), 1)
    body = json_body(_checked(response))
    return body["results"]


async def get(http: httpx.AsyncClient, article_id: str) -> dict | None:
    """One article by its bare DOAJ id, or None when DOAJ has no such article."""
    response = await http.get(f"/articles/{article_id}")
    if response.status_code == 404:
        return None
    return json_body(_checked(response))


async def search_page(
    http: httpx.AsyncClient, term: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    """`cursor` is a 1-based page number (DOAJ's own convention; the registry seeds it at 1 via
    starting_cursor). Returns (entries, next_page_or_None) -- "is there more" is answered directly by
    whether the response's own "next" key is present, so there's no count/page-size arithmetic to get
    wrong."""
    response = await _search(http, term, page_size, cursor)
    body = json_body(_checked(response))
    next_cursor = cursor + 1 if "next" in body and cursor * page_size < MAX_RESULTS else None
    return body["results"], next_cursor
