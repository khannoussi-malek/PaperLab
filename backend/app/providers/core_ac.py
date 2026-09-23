"""CORE over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed on 2026-09-17 without a key: `/v3/search/works` answers 301 to `/v3/search/works/`, so the client asks for the
slash path directly. `x-ratelimit-limit` is 10. A bad key answers 401, and a query its parser can't read answers 500.
Named core_ac because `core` would read as app.core.
"""

import httpx

from app.providers.arxiv import title_words
from app.providers.openalex import json_body

BASE_URL = "https://api.core.ac.uk"
TIMEOUT = httpx.Timeout(10.0)


def new_client(api_key: str | None, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    # The key rides in a header: httpx puts the URL, query string included, in its error messages.
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=TIMEOUT, transport=transport)


# ponytail: no retry on 429, as in openalex.py. A free key raises the limit.


async def search(http: httpx.AsyncClient, title: str, limit: int) -> list[dict]:
    """CORE's raw works. Expect duplicate records of one paper, authors out of order and late years."""
    # Title words ANDed: the plain words matched 167M works and missed BERT; a quoted phrase matched 78M.
    words = title_words(title)
    if not words:
        return []
    params = {"q": f"title:({' AND '.join(words)})", "limit": limit}
    response = await http.get("/v3/search/works/", params=params)
    return json_body(response.raise_for_status())["results"]


async def search_page(http: httpx.AsyncClient, title: str, page_size: int, cursor: int) -> tuple[list[dict], int | None]:
    """One page of CORE results."""
    words = title_words(title)
    if not words:
        return [], None
    params = {"q": f"title:({' AND '.join(words)})", "limit": page_size, "offset": cursor}
    response = await http.get("/v3/search/works/", params=params)
    body = json_body(response.raise_for_status())
    results = body["results"]
    next_cursor = cursor + page_size if cursor + page_size < body["totalHits"] else None
    return results, next_cursor
