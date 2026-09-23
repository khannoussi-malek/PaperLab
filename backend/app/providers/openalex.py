"""OpenAlex over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Since February 2026 OpenAlex is metered: $0.10 of use a day without an API key, $1 a day with a free key, a paid
plan beyond that. Measured on 2026-09-13 without a key: a singleton lookup costs 0 credits, a filter list 1 and a
`.search` filter 10, out of 1,000 free credits ($0.10) a day. Bursts over 10 requests per second get HTTP 429. A
missing work answers 404 with an HTML body. Probed on 2026-09-17: a bad key, sent either as `api_key` or as
`Authorization: Bearer`, answers 401.
"""

import re
from typing import Any
from urllib.parse import quote

import httpx

BASE_URL = "https://api.openalex.org"
TIMEOUT = httpx.Timeout(10.0)
SEARCH_RESULTS = 5
AUTHOR_BATCH = 50
# `select` keeps responses small and costs nothing extra. These are the only fields enrichment reads.
WORK_FIELDS = ",".join(
    [
        "id", "doi", "title", "publication_year", "type", "is_retracted", "open_access", "best_oa_location",
        "primary_location", "cited_by_count", "referenced_works_count", "authorships", "topics", "keywords",
        "concepts", "abstract_inverted_index", "locations",
    ]
)  # fmt: skip
AUTHOR_FIELDS = ",".join(
    [
        "id", "orcid", "display_name", "display_name_alternatives", "works_count", "cited_by_count", "summary_stats",
        "last_known_institutions", "topics",
    ]
)  # fmt: skip


def new_client(
    mailto: str | None, transport: httpx.AsyncBaseTransport | None = None, api_key: str | None = None
) -> httpx.AsyncClient:
    # Client-level params are merged into every request, so no call can leave out mailto once it's set.
    params = {"mailto": mailto} if mailto else {}
    # The key rides in a header, never the query string: httpx puts the URL in its error messages, which enrichment
    # logs with logger.exception.
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    # follow_redirects: OpenAlex answers a merged-away work id with a 301 to the record it merged into.
    return httpx.AsyncClient(
        base_url=BASE_URL, params=params, headers=headers, timeout=TIMEOUT, transport=transport, follow_redirects=True
    )


# ponytail: no retry, not even on a 429. Enrichment is non-fatal and a re-ingest looks the paper up again. Add one
# Retry-After wait here if bulk uploads start coming back without metadata.


def json_body(response: httpx.Response) -> Any:
    """response.json(), but a malformed 200 body (a proxy's HTML page, say) raises httpx.HTTPError like every
    other OpenAlex failure, instead of a bare json.JSONDecodeError callers don't expect."""
    try:
        return response.json()
    except ValueError as exc:
        raise httpx.DecodingError(str(exc), request=response.request) from exc


async def get_work(http: httpx.AsyncClient, key: str) -> dict | None:
    """`key` is an OpenAlex work ID ("W2963341956") or "doi:<doi>". None when OpenAlex has no such work."""
    # A DOI can contain "?" or other reserved characters; left bare they'd truncate the path into a query string.
    response = await http.get(f"/works/{quote(key, safe='/:')}", params={"select": WORK_FIELDS})
    if response.status_code == 404:
        return None
    return json_body(response.raise_for_status())


async def search_works(http: httpx.AsyncClient, title: str, per_page: int = SEARCH_RESULTS) -> list[dict]:
    # A comma inside a filter value is rejected with HTTP 400 even when percent-encoded, and "|" means OR.
    query = re.sub(r"[,|]", " ", title)
    params = {"filter": f"title.search:{query}", "per-page": per_page, "select": WORK_FIELDS}
    response = await http.get("/works", params=params)
    return json_body(response.raise_for_status())["results"]


async def get_authors(http: httpx.AsyncClient, openalex_ids: list[str]) -> list[dict]:
    """One request per 50 IDs. Records come back in OpenAlex's order, not the order asked for."""
    records: list[dict] = []
    for start in range(0, len(openalex_ids), AUTHOR_BATCH):
        batch = "|".join(openalex_ids[start : start + AUTHOR_BATCH])
        params = {"filter": f"openalex_id:{batch}", "per-page": AUTHOR_BATCH, "select": AUTHOR_FIELDS}
        response = await http.get("/authors", params=params)
        records += json_body(response.raise_for_status())["results"]
    return records


async def referenced_works(http: httpx.AsyncClient, work_id: str) -> list[str]:
    """The short OpenAlex IDs ("W...") `work_id` lists as its references, no metadata (M7.5 §1). [] when OpenAlex
    has no such work (404)."""
    response = await http.get(f"/works/{quote(work_id, safe='/:')}", params={"select": "referenced_works"})
    if response.status_code == 404:
        return []
    body = json_body(response.raise_for_status())
    # "https://openalex.org/W123" -> "W123"; enrichment.short_id does the same, kept local to avoid an
    # app.providers -> app.core import cycle (enrichment already imports this module).
    return [url.rsplit("/", 1)[-1] for url in body.get("referenced_works") or []]


async def works_by_ids(http: httpx.AsyncClient, ids: list[str]) -> list[dict]:
    """Works by short OpenAlex ID, one request per 50 (mirrors get_authors). OpenAlex's own order, not `ids`'."""
    records: list[dict] = []
    for start in range(0, len(ids), AUTHOR_BATCH):
        batch = "|".join(ids[start : start + AUTHOR_BATCH])
        params = {"filter": f"openalex_id:{batch}", "per-page": AUTHOR_BATCH, "select": WORK_FIELDS}
        response = await http.get("/works", params=params)
        records += json_body(response.raise_for_status())["results"]
    return records


async def citing_works(http: httpx.AsyncClient, work_id: str, limit: int) -> list[dict]:
    """One page of up to `limit` works citing `work_id`, newest first (OpenAlex sorts; D79 caps this direction so
    it is never paged to the end)."""
    params = {
        "filter": f"cites:{work_id}",
        "sort": "publication_date:desc",
        "per-page": min(limit, 200),
        "select": WORK_FIELDS,
    }
    response = await http.get("/works", params=params)
    return json_body(response.raise_for_status())["results"]


async def search_page(http: httpx.AsyncClient, title: str, page_size: int, cursor: int) -> tuple[list[dict], int | None]:
    """One page of OpenAlex results."""
    params = {"filter": f"title.search:{title}", "per-page": page_size, "page": cursor, "select": WORK_FIELDS}
    response = await http.get("/works", params=params)
    body = json_body(response.raise_for_status())
    results = body["results"]
    next_cursor = cursor + 1 if cursor * page_size < body["meta"]["count"] else None
    return results, next_cursor
