"""SSRN via OpenAlex's own API, filtered to SSRN's OpenAlex source id (S4210172589 -- confirmed live).
No new HTTP client or field list: this module reuses openalex.py's own client, WORK_FIELDS and json_body,
since SSRN's metadata already lives in OpenAlex -- there is no separate SSRN API. Confirmed live: SSRN
never carries a usable PDF (best_oa_location.pdf_url and primary_location.pdf_url are both null even on
is_oa:true records -- only a landing-page link is ever present), so this module does nothing special for
PDFs; from_work's own field reads already only look at the pdf_url fields, which stay empty here exactly
as they should.
"""

import re

import httpx

from app.providers.openalex import WORK_FIELDS, json_body

SSRN_SOURCE_ID = "S4210172589"


def _filter(title: str) -> str:
    # Same comma-removal openalex.py's own search_works() already applies: a literal comma in a filter
    # value is rejected even percent-encoded, and "|" means OR -- stripped here before adding the SSRN
    # clause, the same way the parent function strips it before adding its own single clause.
    query = re.sub(r"[,|]", " ", title)
    return f"title.search:{query},locations.source.id:{SSRN_SOURCE_ID}"


async def search(http: httpx.AsyncClient, title: str, per_page: int) -> list[dict]:
    params = {"filter": _filter(title), "per-page": per_page, "select": WORK_FIELDS}
    response = await http.get("/works", params=params)
    return json_body(response.raise_for_status())["results"]


async def search_page(
    http: httpx.AsyncClient, title: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    params = {"filter": _filter(title), "per-page": page_size, "page": cursor // page_size + 1, "select": WORK_FIELDS}
    response = await http.get("/works", params=params)
    body = json_body(response.raise_for_status())
    results = body["results"]
    next_cursor = cursor + page_size if cursor + page_size < body["meta"]["count"] else None
    return results, next_cursor


async def get_work(http: httpx.AsyncClient, key: str) -> dict | None:
    """One work by its OpenAlex id (e.g. "W1990513740"). None when OpenAlex has no such work. No filter
    applied here: a direct id lookup already names one exact record."""
    response = await http.get(f"/works/{key}")
    if response.status_code == 404:
        return None
    return json_body(response.raise_for_status())
