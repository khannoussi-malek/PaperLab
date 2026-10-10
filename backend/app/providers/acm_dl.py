"""ACM DL via Crossref's own API, filtered to the ACM DOI prefix (10.1145 -- confirmed live to be solely
ACM's own, no ambiguity with another publisher). No new HTTP client or field list: this module reuses
crossref.py's own client, FIELDS and json_body, since ACM's metadata already lives in Crossref -- there is
no separate ACM DL API. Only ~16% of ACM works carry an abstract (measured live); the DL's own PDF link
requires a similarity-checking partnership and answers a Cloudflare 403 in practice, matching crossref.py's
own "no PDF" rule.
"""

from urllib.parse import quote

import httpx

from app.providers.crossref import FIELDS
from app.providers.openalex import json_body

ACM_FILTER = "prefix:10.1145"


async def search(http: httpx.AsyncClient, title: str, rows: int) -> list[dict]:
    params = {"query.bibliographic": title, "filter": ACM_FILTER, "rows": rows, "select": FIELDS}
    response = await http.get("/works", params=params)
    return json_body(response.raise_for_status())["message"]["items"]


async def search_page(
    http: httpx.AsyncClient, title: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    params = {
        "query.bibliographic": title, "filter": ACM_FILTER, "rows": page_size, "offset": cursor, "select": FIELDS,
    }
    response = await http.get("/works", params=params)
    items = json_body(response.raise_for_status())["message"]["items"]
    next_cursor = cursor + page_size if len(items) == page_size else None
    return items, next_cursor


async def get_work(http: httpx.AsyncClient, doi: str) -> dict | None:
    """The ACM work for `doi`, or None when Crossref has no such DOI. The prefix filter is not applied
    here: a direct DOI lookup already names one exact record, so there is nothing left to filter."""
    response = await http.get(f"/works/{quote(doi, safe='/:')}")
    if response.status_code == 404:
        return None
    return json_body(response.raise_for_status())["message"]
