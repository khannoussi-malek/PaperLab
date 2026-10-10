"""HAL (https://api.archives-ouvertes.fr/search/), the French national open-access repository. Network
failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed live on 2026-10-09: one-step search (GET /search/?q=...&wt=json), like Zenodo -- no separate fetch
step. The default response is nearly useless for this module's purposes (just docid/label_s/uri_s, where
label_s is one unstructured citation string) -- real structured fields need an explicit fl= parameter
(Solr convention): title_s, abstract_s, authFullName_s, files_s are Solr multi-valued fields (always a
JSON list, even with one element); doiId_s and producedDate_s come back as plain scalar strings.
abstract_s/doiId_s/files_s are frequently absent on real records (confirmed across several live queries)
-- HAL is a researcher-self-deposit repository, not every record carries every field; this is ordinary
nullability, not a parsing bug. Default sort is already relevance (confirmed live: the default response
and an explicit sort=score+desc give byte-identical top ids, both differing from an explicit newest-first
sort) -- no sort param is sent. An unrecognized sort field is silently ignored (confirmed live: a
nonsense sort value still answers HTTP 200 with normal, correctly-ordered results) -- genuinely different
from both NCBI/EBI's trap and Zenodo's own honest 400; there is nothing to catch here. A GENUINELY
malformed query (broken Solr syntax) answers HTTP 200 with a body-level {"error": {"msg": "..."}}
(confirmed live) -- a plain raise_for_status() would see 200 and do nothing, so the body itself is
checked for an "error" key, the same general shape as PubMed/PMC's ERROR-key trap, just different JSON
keys. Pagination is start/rows. The architecture doc's claimed "10,000-result cap" does NOT exist --
confirmed live by paging a query with 89,136 real results past start=10000, start=50000, all the way to
start=80000: every one returned real, distinct results with no error and no ceiling. "Is there more" is
start + rows < numFound (HAL's own reported total), trusted directly, with no artificial cap. No key, no
documented rate limit, and none observed during this research -- paced as politely as every other
keyless, undocumented-limit source in this codebase (Europe PMC's own precedent). A lookup by id
(q=docid:<id>) answers HTTP 200 with numFound: 0 and an empty docs list for an unknown id (confirmed
live), not a 404 -- same "empty set, not an error" convention PubMed's own get() already established.
Direct PDF links are real for records with a files_s entry (confirmed live: a genuine content-type:
application/pdf, HTTP 200, no interstitial).
"""

import httpx

from app.providers.arxiv import title_words
from app.providers.http import RateLimited
from app.providers.openalex import json_body

BASE_URL = "https://api.archives-ouvertes.fr/search"
TIMEOUT = httpx.Timeout(10.0)
_MIN_INTERVAL = 1 / 3  # no documented limit; paced as politely as Europe PMC's own keyless default

_FIELDS = "docid,title_s,abstract_s,authFullName_s,doiId_s,producedDate_s,files_s"


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # HAL takes neither a contact email nor an API key; both parameters exist only to satisfy the uniform
    # new_client(*, email=None, api_key=None, transport=None) signature every provider shares.
    if transport is None:
        limited = RateLimited(httpx.AsyncHTTPTransport(), _MIN_INTERVAL)
    else:
        limited = RateLimited(transport, _MIN_INTERVAL)
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=limited)


def _checked_body(response: httpx.Response) -> dict:
    """Like response.raise_for_status() plus a check of the body itself: HAL answers a genuinely
    malformed query with HTTP 200 and a body-level {"error": {"msg": ...}}, the same "200 but the body
    says otherwise" shape NCBI's own esearch has, just with different keys. The message never embeds the
    request URL, matching every provider's own convention."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"HAL answered HTTP {response.status_code}", request=response.request, response=response
        )
    body = json_body(response)
    if "error" in body:
        raise httpx.DecodingError(str(body["error"].get("msg", body["error"])), request=response.request)
    return body


async def _search(http: httpx.AsyncClient, term: str, rows: int, start: int) -> httpx.Response:
    return await http.get("/", params={"q": term, "rows": rows, "start": start, "wt": "json", "fl": _FIELDS})


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    words = title_words(term)
    if not words:
        return []
    response = await _search(http, " ".join(words), limit, 0)
    body = _checked_body(response)
    return [_entry(doc) for doc in body["response"]["docs"]]


async def get(http: httpx.AsyncClient, docid: str) -> dict | None:
    """One paper by its bare numeric HAL docid, or None when HAL has no such record."""
    response = await http.get("/", params={"q": f"docid:{docid}", "rows": 1, "wt": "json", "fl": _FIELDS})
    docs = _checked_body(response)["response"]["docs"]
    return _entry(docs[0]) if docs else None


async def search_page(
    http: httpx.AsyncClient, term: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    """`cursor` is `start` (0-based, HAL's own convention). Returns (entries, next_cursor_or_None) --
    trusts HAL's own reported numFound directly, confirmed live to have no real pagination ceiling (the
    architecture doc's claimed 10,000-result cap does not exist)."""
    response = await _search(http, term, page_size, cursor)
    body = _checked_body(response)
    entries = [_entry(doc) for doc in body["response"]["docs"]]
    next_cursor = cursor + page_size if cursor + page_size < body["response"]["numFound"] else None
    return entries, next_cursor


def _entry(doc: dict) -> dict:
    authors = doc.get("authFullName_s") or []
    titles = doc.get("title_s") or []
    abstracts = doc.get("abstract_s") or []
    files = doc.get("files_s") or []
    year_str = (doc.get("producedDate_s") or "")[:4]
    return {
        "docid": doc["docid"],
        "title": titles[0] if titles else "",
        "authors": authors,
        "year": int(year_str) if year_str.isdigit() else None,
        "doi": (doc.get("doiId_s") or "").strip().lower() or None,
        "abstract": " ".join(abstracts).strip() or None,
        "pdf_url": files[0] if files else None,
    }
