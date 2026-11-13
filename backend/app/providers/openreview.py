"""OpenReview (https://api2.openreview.net/notes/search). Network failures, timeouts and error statuses raise
httpx.HTTPError. A 429 is retried once after its Retry-After (capped at one window); a second 429 raises, so the
run marks this source failed for the pass instead of reporting an empty search.

Probed live on 2026-11-13: keyless, `type` must be one of prefix|terms|exact (type=all answers HTTP 400), content
values come back as {"value": ...} objects, `count` is the total and `offset` pages it. Rate limit from the
`ratelimit-policy: 20;w=60` header: 20 requests per 60 seconds, shared by every OpenReview request in this process,
hence the module-level token bucket below.
"""

import asyncio
import time
from collections import deque

import httpx

from app.providers.http import retrying
from app.providers.openalex import json_body

BASE_URL = "https://api2.openreview.net"
TIMEOUT = httpx.Timeout(10.0)
RATE_LIMIT = 20  # requests per window, from the ratelimit-policy header
RATE_WINDOW_SECONDS = 60.0
_sent_at: deque[float] = deque()  # monotonic send times of the requests inside the current window


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # OpenReview takes no key and no email for search; both parameters exist only to satisfy the uniform
    # new_client(*, email=None, api_key=None, transport=None) signature every provider shares.
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=retrying(transport))


async def _wait(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _take_token() -> None:
    """Waits until fewer than RATE_LIMIT requests were sent in the last window. No lock is needed: nothing awaits
    between the check and the append, so asyncio cannot interleave two callers there."""
    while True:
        now = time.monotonic()
        while _sent_at and now - _sent_at[0] >= RATE_WINDOW_SECONDS:
            _sent_at.popleft()
        if len(_sent_at) < RATE_LIMIT:
            _sent_at.append(now)
            return
        await _wait(RATE_WINDOW_SECONDS - (now - _sent_at[0]))


def _retry_after_seconds(response: httpx.Response) -> float:
    """The Retry-After seconds, capped at one window so a single answer cannot stall a run for hours. Missing or
    unreadable (an HTTP date, say) means one window."""
    try:
        return min(float(response.headers.get("retry-after", RATE_WINDOW_SECONDS)), RATE_WINDOW_SECONDS)
    except ValueError:
        return RATE_WINDOW_SECONDS


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL -- same convention
    every provider in this codebase follows."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"OpenReview answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


async def _get(http: httpx.AsyncClient, params: dict) -> httpx.Response:
    """One search request through the shared budget. A 429 waits its Retry-After once and tries again; a second
    429 comes back as-is for _checked to turn into the error that fails the source."""
    await _take_token()
    response = await http.get("/notes/search", params=params)
    if response.status_code == 429:
        await _wait(_retry_after_seconds(response))
        await _take_token()
        response = await http.get("/notes/search", params=params)
    return response


def _params(term: str, limit: int, offset: int) -> dict:
    # Title search over forum notes. Reviews, comments and decisions also match, and from_openreview drops them.
    return {"term": term, "type": "terms", "content": "title", "source": "forum", "limit": limit, "offset": offset}


def _notes(body) -> list[dict]:
    """The reply's notes; a reply without them is a failed source, not an empty result."""
    notes = body.get("notes") if isinstance(body, dict) else None
    if not isinstance(notes, list):
        raise httpx.DecodingError("OpenReview replied without a notes list")
    return notes


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    return _notes(json_body(_checked(await _get(http, _params(term, limit, 0)))))


async def search_page(http: httpx.AsyncClient, term: str, page_size: int, cursor: int) -> tuple[list[dict], int | None]:
    """`cursor` is a 0-based offset into the results (the registry's default starting_cursor of 0). Returns
    (notes, next_offset_or_None): more remain while the offset is still short of the reported `count`."""
    body = json_body(_checked(await _get(http, _params(term, page_size, cursor))))
    notes = _notes(body)
    more = bool(notes) and cursor + page_size < (body.get("count") or 0)
    return notes, cursor + page_size if more else None
