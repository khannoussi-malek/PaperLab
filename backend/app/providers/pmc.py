"""PMC (NCBI E-utilities, db=pmc) over HTTP. Network failures, timeouts and error statuses (429 included)
raise httpx.HTTPError.

Probed live on 2026-10-09: same two-step esearch/efetch dance as PubMed (db=pubmed), just db=pmc -- ids
from esearch are bare numeric PMC ids (e.g. "13647476"), and efetch's own JATS XML tags each record with
the "PMC"-prefixed form (<article-id pub-id-type="pmcid">PMC13647476</article-id>). No namespace, same
as PubMed's own schema, but a different one (JATS: <article>, <front/article-meta>, <article-id
pub-id-type="pmid"|"doi"|"pmcid">, <contrib-group>/<contrib>/<name>/<surname>/<given-names>,
<abstract><title>ABSTRACT</title><p>...</p></abstract> -- the nested <title> label must be skipped, or
every abstract gets the literal word "ABSTRACT" prepended; confirmed by testing against a real,
downloaded record before writing this). esearch shares every one of PubMed's own NCBI quirks: defaults
to newest-first (sort=relevance requested explicitly), and the documented HTTP-200 {"ERROR": ...} reply
for a malformed query/empty term/retstart>9998 is handled the same way (raise on the ERROR key; the
9998-cap variant's own malformed-JSON body is already caught one level up by json_body()'s existing
ValueError handling). An unknown PMC id answers HTTP 200 with <pmc-articleset><error id="...">...
</error></pmc-articleset> (NOT PubMed's silent empty set) -- findall("article") naturally returns [] for
this shape, so no extra handling is needed. No full-text extraction: nothing in this codebase's
Candidate/discovery pipeline stores full text today (ponytail: this stays metadata+abstract, same shape
as every other source -- extend if a later milestone adds a full-text consumer). No PDF: the old PMC OA
Web Service is confirmed gone, and the obvious constructed path
(pmc.ncbi.nlm.nih.gov/articles/PMC<id>/pdf/...) answers HTTP 200 but is a JS proof-of-work interstitial,
not a file (confirmed live). Rate limit: shared with PubMed (same eutils host/key), 3 requests/second
without a key, 10/second with NCBI's own free API key.
"""

import xml.etree.ElementTree as ET

import httpx

from app.providers.http import RateLimited, shared_pacer
from app.providers.openalex import json_body

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = httpx.Timeout(10.0)
_MIN_INTERVAL_NO_KEY = 1 / 3
_MIN_INTERVAL_WITH_KEY = 1 / 10


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    params = {k: v for k, v in {"tool": "paperlab", "email": email, "api_key": api_key}.items() if v}
    min_interval = _MIN_INTERVAL_WITH_KEY if api_key else _MIN_INTERVAL_NO_KEY
    if transport is None:
        # Real network traffic only -- see pubmed.py's own new_client for why (NCBI's rate limit is per
        # IP/key, not per httpx client, but a shared pacer must never leak into a test's own fake/mock
        # transport).
        limited = RateLimited(httpx.AsyncHTTPTransport(), pacer=shared_pacer("eutils", api_key, min_interval))
    else:
        limited = RateLimited(transport, min_interval)
    return httpx.AsyncClient(base_url=BASE_URL, params=params, timeout=TIMEOUT, transport=limited)


def _checked(response: httpx.Response) -> httpx.Response:
    """Like response.raise_for_status(), but the message never embeds the request URL (which would carry
    the NCBI api_key query param) -- same fix PubMed's own final review required, baked in here from the
    start."""
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"PMC answered HTTP {response.status_code}", request=response.request, response=response
        )
    return response


async def _esearch(http: httpx.AsyncClient, term: str, limit: int, start: int) -> tuple[list[str], int]:
    """PMC ids matching `term` (at most `limit`, from `start`), and NCBI's own total count for the query."""
    response = await http.get(
        "/esearch.fcgi",
        params={
            "db": "pmc", "term": term, "retmax": limit, "retstart": start, "retmode": "json",
            "sort": "relevance",
        },
    )
    result = json_body(_checked(response))["esearchresult"]
    if "ERROR" in result:
        raise httpx.DecodingError(result["ERROR"], request=response.request)
    return result["idlist"], int(result["count"])


async def _efetch(http: httpx.AsyncClient, ids: list[str]) -> list[dict]:
    """The full records for `ids`, one batched request, reordered to match `ids`' own order. efetch's own
    response order doesn't always match the ids it was asked for (confirmed live), and esearch's own
    ranking (by relevance, see sort=relevance above) is what callers rely on being preserved. `ids` must
    be non-empty -- callers check first."""
    response = await http.get("/efetch.fcgi", params={"db": "pmc", "id": ",".join(ids), "retmode": "xml"})
    by_id = {entry["pmcid"]: entry for entry in _entries(_checked(response))}
    return [by_id[pmcid] for pmcid in ids if pmcid in by_id]


async def search(http: httpx.AsyncClient, term: str, limit: int) -> list[dict]:
    ids, _ = await _esearch(http, term, limit, start=0)
    return await _efetch(http, ids) if ids else []


async def get(http: httpx.AsyncClient, pmcid: str) -> dict | None:
    """One paper by its bare numeric PMC id (no "PMC" prefix), or None when PMC has no such record."""
    entries = await _efetch(http, [pmcid])
    return entries[0] if entries else None


async def search_page(
    http: httpx.AsyncClient, term: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    ids, count = await _esearch(http, term, page_size, start=cursor)
    entries = await _efetch(http, ids) if ids else []
    # ponytail: NCBI's ESearch hard ceiling (retstart can't exceed 9998), same as pubmed.py.
    next_cursor = cursor + page_size if cursor + page_size < min(count, 9999) else None
    return entries, next_cursor


def _text(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _entries(response: httpx.Response) -> list[dict]:
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise httpx.DecodingError(str(exc), request=response.request) from exc
    if root.tag != "pmc-articleset":
        raise httpx.DecodingError("PMC's answer is not a pmc-articleset", request=response.request)
    return [entry for node in root.findall("article") if (entry := _entry(node))]


def _entry(node: ET.Element) -> dict | None:
    meta = node.find("front/article-meta")
    if meta is None:
        return None
    pmcid = next((el.text for el in meta.findall("article-id") if el.get("pub-id-type") == "pmcid"), None)
    if not pmcid:
        return None
    pmid = next((el.text for el in meta.findall("article-id") if el.get("pub-id-type") == "pmid"), None)
    doi = next((el.text for el in meta.findall("article-id") if el.get("pub-id-type") == "doi"), None)
    title_el = meta.find("title-group/article-title")
    year = meta.findtext("pub-date/year")
    authors = [
        joined
        for contrib in meta.findall("contrib-group/contrib[@contrib-type='author']")
        if (joined := " ".join(filter(None, (contrib.findtext("name/given-names"), contrib.findtext("name/surname")))))
    ]
    abstract_el = meta.find("abstract")
    # .iter("p"), not .findall("p") -- most clinical/review abstracts are structured
    # (<abstract><sec><title>Background</title><p>...</p></sec>...</abstract>), so the real <p> text is
    # nested under <sec>, not a direct child of <abstract>. .iter() finds a <p> at any depth; it still
    # only visits <p> elements, so no <title>/<sec> label text leaks in (same guarantee findall("p") had
    # for the flat case). Confirmed against 20 real records: 0/20 empty, 0 label leaks, after this fix.
    abstract = " ".join(_text(p) for p in abstract_el.iter("p")) if abstract_el is not None else ""
    return {
        "pmcid": pmcid.removeprefix("PMC"),
        "pmid": pmid,
        "title": _text(title_el) if title_el is not None else "",
        "authors": authors,
        "year": int(year) if year and year.isdigit() else None,
        "doi": doi.strip().lower() if doi else None,
        "abstract": abstract or None,
    }
