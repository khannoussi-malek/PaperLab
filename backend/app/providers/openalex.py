"""OpenAlex over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Measured on 2026-09-13 without an API key: a singleton lookup costs 0 credits, a filter list 1 and a `.search`
filter 10, out of 1,000 free credits a day. Bursts over 10 requests per second get HTTP 429. A missing work answers
404 with an HTML body.
"""

import re

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
        "concepts", "abstract_inverted_index",
    ]
)  # fmt: skip
AUTHOR_FIELDS = ",".join(
    [
        "id", "orcid", "display_name", "display_name_alternatives", "works_count", "cited_by_count", "summary_stats",
        "last_known_institutions", "topics",
    ]
)  # fmt: skip


def new_client(mailto: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    # Client-level params are merged into every request, so no call can leave out mailto.
    return httpx.AsyncClient(base_url=BASE_URL, params={"mailto": mailto}, timeout=TIMEOUT, transport=transport)


# ponytail: no retry, not even on a 429. Enrichment is non-fatal and a re-ingest looks the paper up again. Add one
# Retry-After wait here if bulk uploads start coming back without metadata.


async def get_work(http: httpx.AsyncClient, key: str) -> dict | None:
    """`key` is an OpenAlex work ID ("W2963341956") or "doi:<doi>". None when OpenAlex has no such work."""
    response = await http.get(f"/works/{key}", params={"select": WORK_FIELDS})
    if response.status_code == 404:
        return None
    return response.raise_for_status().json()


async def search_works(http: httpx.AsyncClient, title: str) -> list[dict]:
    # A comma inside a filter value is rejected with HTTP 400 even when percent-encoded, and "|" means OR.
    query = re.sub(r"[,|]", " ", title)
    params = {"filter": f"title.search:{query}", "per-page": SEARCH_RESULTS, "select": WORK_FIELDS}
    return (await http.get("/works", params=params)).raise_for_status().json()["results"]


async def get_authors(http: httpx.AsyncClient, openalex_ids: list[str]) -> list[dict]:
    """One request per 50 IDs. Records come back in OpenAlex's order, not the order asked for."""
    records: list[dict] = []
    for start in range(0, len(openalex_ids), AUTHOR_BATCH):
        batch = "|".join(openalex_ids[start : start + AUTHOR_BATCH])
        params = {"filter": f"openalex_id:{batch}", "per-page": AUTHOR_BATCH, "select": AUTHOR_FIELDS}
        records += (await http.get("/authors", params=params)).raise_for_status().json()["results"]
    return records
