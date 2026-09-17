"""Crossref over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed on 2026-09-17: without `mailto` a request goes to the public pool (1 request a second; a burst got 429), with
it to the polite pool (3 a second). An unknown DOI answers 404 with a plain-text body.
"""

from urllib.parse import quote

import httpx

from app.providers.openalex import json_body

BASE_URL = "https://api.crossref.org"
TIMEOUT = httpx.Timeout(10.0)
# `select` works on searches only. These are the only fields the candidate mapper reads.
FIELDS = "DOI,title,author,issued,container-title,is-referenced-by-count,type"


def new_client(mailto: str | None, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    params = {"mailto": mailto} if mailto else {}
    return httpx.AsyncClient(base_url=BASE_URL, params=params, timeout=TIMEOUT, transport=transport)


# ponytail: no retry on 429, as in openalex.py. The contact email moves requests to the faster polite pool.


async def search(http: httpx.AsyncClient, title: str, rows: int) -> list[dict]:
    """Crossref's raw items, best match first. Its matching is loose: expect non-papers and namesakes."""
    params = {"query.bibliographic": title, "rows": rows, "select": FIELDS}
    response = await http.get("/works", params=params)
    return json_body(response.raise_for_status())["message"]["items"]


async def get_work(http: httpx.AsyncClient, doi: str) -> dict | None:
    """The work for `doi`, or None when Crossref has no such DOI."""
    # A DOI can contain "?" or other reserved characters; left bare they'd truncate the path into a query string.
    response = await http.get(f"/works/{quote(doi, safe='/:')}")
    if response.status_code == 404:
        return None
    return json_body(response.raise_for_status())["message"]
