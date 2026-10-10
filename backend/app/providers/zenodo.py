"""Zenodo (https://zenodo.org/api/records). Network failures, timeouts and error statuses (429 included)
raise httpx.HTTPError.

Probed live on 2026-10-09: one-step search (GET /api/records?q=...), unlike PubMed/PMC's esearch-then-
efetch dance -- no separate fetch step. type=publication&subtype=article filters out the dataset/
software/market-research-report noise that leaks through on a bare query (confirmed live: an unfiltered
"CRISPR gene editing" query's own top hit was a commercial market-research dataset, not a paper -- every
request here sends this filter). Default sort is already relevance (confirmed live: the default response
and an explicit sort=bestmatch give byte-identical top ids) -- no sort param is sent. An invalid sort
value answers a real, clearly-worded HTTP 400 ("Invalid sort option '...'."), not a misleading generic
error -- tried this deliberately and there is no EBI-style trap here. Pagination is page/size, with a
real anonymous cap of exactly 25 per page (confirmed: size=26 answers HTTP 400, "Page size cannot be
greater than 25. Please use authenticated requests to increase the limit to 100." -- this is why this
source is keyed, not keyless, despite the architecture doc's own "keyless" summary); "is there more" is
answered directly by whether the response's own links.next key is present (confirmed count-aware, not
page-fullness-based, at an exact boundary). Records embed their own files list with a direct, real,
fetchable PDF link for open-access records (confirmed live: a genuine content-type: application/
octet-stream download matching the metadata's own reported size, no interstitial -- unlike Europe PMC's
own equivalent claim, which turned out to be Cloudflare-blocked). Rate limit: documented 30 requests/
minute for search (confirmed live via the response's own X-RateLimit-Limit/Remaining headers), 60/minute
general, 2000/hour. An unknown record id answers a clean HTTP 404 (confirmed live), unlike PubMed/PMC's
own silent-empty-set convention.
"""

import html
import re

import httpx

from app.providers.http import RateLimited
from app.providers.openalex import json_body

BASE_URL = "https://zenodo.org/api"
TIMEOUT = httpx.Timeout(10.0)
_MIN_INTERVAL = 60 / 30  # the documented 30 requests/minute search limit
MAX_PAGE_SIZE = 25  # anonymous cap (confirmed live); a configured api_key raises this to 100 at Zenodo's
# end, but this module always requests at most 25 -- wiring a dynamic page_size per key is not yet needed
# by anything in this codebase (ponytail: add it if a later milestone needs Zenodo pages bigger than 25).

_TAG = re.compile(r"</?[A-Za-z][\w:-]*(?:\s[^<>]*)?/?>")


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # Zenodo's token isn't wired up yet (see MAX_PAGE_SIZE's own note) -- api_key/email exist only to
    # satisfy the uniform new_client(*, email=None, api_key=None, transport=None) signature every
    # provider shares.
    if transport is None:
        limited = RateLimited(httpx.AsyncHTTPTransport(), _MIN_INTERVAL)
    else:
        limited = RateLimited(transport, _MIN_INTERVAL)
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=limited)


def _clean(text: str | None) -> str:
    return " ".join(_TAG.sub("", html.unescape(text or "")).split())


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL -- same convention
    every provider in this codebase follows."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"Zenodo answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


async def _search(http: httpx.AsyncClient, term: str, page_size: int, page: int) -> httpx.Response:
    return await http.get(
        "/records",
        params={"q": term, "type": "publication", "subtype": "article", "size": page_size, "page": page},
    )


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    response = await _search(http, term, min(limit, MAX_PAGE_SIZE), 1)
    body = json_body(_checked(response))
    return [_entry(hit) for hit in body["hits"]["hits"]]


async def get(http: httpx.AsyncClient, record_id: str) -> dict | None:
    """One paper by its Zenodo numeric record id, or None when Zenodo has no such record."""
    response = await http.get(f"/records/{record_id}")
    if response.status_code == 404:
        return None
    return _entry(json_body(_checked(response)))


async def search_page(
    http: httpx.AsyncClient, term: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    """`cursor` is a 1-based page number (Zenodo's own convention; the registry seeds it at 1 via
    starting_cursor). Returns (entries, next_page_or_None) -- "is there more" is answered directly by
    whether the response's own links.next key is present, so there's no count/page-size arithmetic to
    get wrong."""
    response = await _search(http, term, page_size, cursor)
    body = json_body(_checked(response))
    entries = [_entry(hit) for hit in body["hits"]["hits"]]
    next_cursor = cursor + 1 if "next" in body.get("links", {}) else None
    return entries, next_cursor


def _entry(raw: dict) -> dict:
    meta = raw.get("metadata", {})
    authors = [a["name"] for a in meta.get("creators", []) if a.get("name")]
    pub_date = meta.get("publication_date") or ""
    year = int(pub_date[:4]) if pub_date[:4].isdigit() else None
    files = raw.get("files") or []
    pdf_url = next((f["links"]["self"] for f in files if f.get("key", "").lower().endswith(".pdf")), None)
    return {
        "id": str(raw["id"]),
        "title": _clean(meta.get("title")),
        "authors": authors,
        "year": year,
        "doi": (raw.get("doi") or "").strip().lower() or None,
        "abstract": _clean(meta.get("description")) or None,
        "pdf_url": pdf_url,
    }
