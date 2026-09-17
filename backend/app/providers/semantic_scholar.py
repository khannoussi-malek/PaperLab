"""Semantic Scholar over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed on 2026-09-16 without an API key: recommendations take a `DOI:<doi>` or `arXiv:<id>` key (an arXiv DOI is a
404), an unknown paper answers 404 with a JSON body, and the shared unauthenticated pool answers 429 when busy.
"""

from urllib.parse import quote

import httpx

from app.providers.openalex import json_body

BASE_URL = "https://api.semanticscholar.org"
TIMEOUT = httpx.Timeout(10.0)
PAPER_FIELDS = "title,year,venue,authors,externalIds,openAccessPdf,citationCount"
# The default pool is recent papers only, and its picks for BERT were weak. all-cs also served a biology DOI.
RECOMMENDATION_POOL = "all-cs"


def new_client(api_key: str | None, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    headers = {"x-api-key": api_key} if api_key else {}
    return httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=TIMEOUT, transport=transport)


# ponytail: no retry on 429, as in openalex.py. A key saved in Settings → Paper sources lifts the shared pool's limit.


async def recommend(http: httpx.AsyncClient, key: str, limit: int) -> list[dict] | None:
    """Papers like `key`: "DOI:<doi>", "arXiv:<id>" or a Semantic Scholar paper id. None when S2 doesn't know it."""
    response = await http.get(
        f"/recommendations/v1/papers/forpaper/{quote(key, safe='/:')}",
        params={"from": RECOMMENDATION_POOL, "limit": limit, "fields": PAPER_FIELDS},
    )
    if response.status_code == 404:
        return None
    return json_body(response.raise_for_status())["recommendedPapers"]


async def match_title(http: httpx.AsyncClient, title: str) -> str | None:
    """The Semantic Scholar paper id of the best match for `title`, or None when nothing matches."""
    response = await http.get("/graph/v1/paper/search/match", params={"query": title, "fields": "paperId"})
    if response.status_code == 404:
        return None
    matches = json_body(response.raise_for_status()).get("data") or []
    return matches[0]["paperId"] if matches else None


async def get_paper(http: httpx.AsyncClient, key: str) -> dict | None:
    """One paper by "arXiv:<id>", "DOI:<doi>" or a Semantic Scholar id. None when S2 doesn't know it."""
    response = await http.get(f"/graph/v1/paper/{quote(key, safe='/:')}", params={"fields": PAPER_FIELDS})
    if response.status_code == 404:
        return None
    return json_body(response.raise_for_status())


async def get_papers(http: httpx.AsyncClient, keys: list[str]) -> list[dict | None]:
    """Several papers in one request, in the order of `keys`; None for each one S2 doesn't know. At most 500 keys."""
    if not keys:
        return []
    response = await http.post("/graph/v1/paper/batch", params={"fields": PAPER_FIELDS}, json={"ids": keys})
    papers = json_body(response.raise_for_status())
    if not isinstance(papers, list):
        raise httpx.DecodingError("Semantic Scholar's batch answer is not a list", request=response.request)
    return papers
