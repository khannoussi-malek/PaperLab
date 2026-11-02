"""arXiv over HTTP. Network failures, timeouts and error statuses (429 included) raise httpx.HTTPError.

Probed on 2026-09-17: answers are Atom feeds. An unknown but well-formed ID is an empty feed; a malformed one (the
discovery regex lets `hep-th/9999999` through) is a 400 whose feed holds one entry titled "Error". arXiv asks for at
most one request every 3 seconds; a long run of requests 3.1 seconds apart got 429.
"""

import re
import xml.etree.ElementTree as ET

import httpx

from app.providers.http import paced, retrying

BASE_URL = "https://export.arxiv.org"
TIMEOUT = httpx.Timeout(10.0)
MAX_TITLE_WORDS = 12
WIDEN_BELOW = 25  # an every-word result under this also takes the top of the any-word list
WIDEN_RESULTS = 40
WIDER_CURSOR = 1_000_000  # a `start` no real search reaches, so a stored cursor says which stage it is in
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
# arXiv's title index leaves these out, so `ti:of` matches nothing and empties the whole AND query (probed
# 2026-09-17, each against `ti:learning`). CORE's parser reads and/or/not, in any case, as operators and answers 500.
STOPWORDS = frozenset(
    "a an and are as at be but by for if in into is it no not of on or such that the their then there these they "
    "this to was will with".split()
)
# An "Error" entry's <id> is https://arxiv.org/api/errors#…, so only real papers match.
_ABS_ID = re.compile(r"arxiv\.org/abs/(.+?)(?:v\d+)?$")


def new_client(
    *, email: str | None = None, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    # arXiv asks for one request every 3 seconds; parallel search runs reached 429s without a budget they all share.
    return httpx.AsyncClient(
        base_url=BASE_URL, timeout=TIMEOUT, transport=transport or paced("arxiv", retrying(None))
    )


# ponytail: no retry on 429, as in openalex.py.


def title_words(title: str) -> list[str]:
    """The words a title search ANDs together: lowercase, no stopwords, at most MAX_TITLE_WORDS. CORE uses it too."""
    return [word for word in re.findall(r"\w+", title.lower()) if word not in STOPWORDS][:MAX_TITLE_WORDS]


async def search(http: httpx.AsyncClient, title: str, limit: int, author: str | None = None) -> list[dict]:
    # `ti:` word by word, not a quoted phrase, so a partial title still matches. `all:` ranked unrelated papers first.
    # `author` (a surname) narrows a short title: "REAL Sampling" alone ranks other papers first.
    words = title_words(title)
    if not words:
        return []
    query = " AND ".join([*(f"ti:{word}" for word in words), *(f"au:{word}" for word in title_words(author or ""))])
    response = await http.get("/api/query", params={"search_query": query, "max_results": limit})
    return _entries(response.raise_for_status())


async def get(http: httpx.AsyncClient, arxiv_id: str) -> dict | None:
    """One paper by arXiv ID, or None when arXiv has no such ID or rejects its format."""
    response = await http.get("/api/query", params={"id_list": arxiv_id})
    if response.status_code == 400:  # the ID is the only thing sent, so a 400 means arXiv can't read it
        return None
    entries = _entries(response.raise_for_status())
    return entries[0] if entries else None


async def get_many(http: httpx.AsyncClient, ids: list[str]) -> list[dict]:
    """The papers arXiv knows among `ids` (one request; callers keep it to 100). Unknown or malformed ids are left
    out. Raises httpx.HTTPStatusError on an error status, so the caller can back off on 429/503."""
    response = await http.get("/api/query", params={"id_list": ",".join(ids), "max_results": len(ids)})
    return _entries(response.raise_for_status())


async def search_page(
    http: httpx.AsyncClient, topic: str, page_size: int, cursor: int
) -> tuple[list[dict], int | None]:
    """One page of a search run's arXiv results, best first: every word of `topic` in any field, then, when that finds
    fewer than WIDEN_BELOW, the best WIDEN_RESULTS with any of the words. `cursor` is `start`, offset by WIDER_CURSOR in
    the wider stage; returns (entries, next_cursor_or_None).

    Why (D288, measured 2026-11-02 on six real topics, results of 50 naming both the topic and its field): any-word
    gave 3-17 at 279,000+ matches, every-word 45-50 where it finds enough. Every-word alone finds 1 for "software design
    creativity fixation" and misses the two papers a reader wants for "mode collapse RLHF diversity", which any-word
    ranks in its top 8, so a thin result takes only the top of the wider list, whose quality falls off fast."""
    words = title_words(topic)
    if not words:
        return [], None
    if cursor >= WIDER_CURSOR:
        start = cursor - WIDER_CURSOR
        entries = await _topic_page(http, " OR ".join(f"all:{word}" for word in words), start, page_size)
        more = len(entries) == page_size and start + page_size < WIDEN_RESULTS
        return entries, cursor + page_size if more else None
    entries = await _topic_page(http, " AND ".join(f"all:{word}" for word in words), cursor, page_size)
    if len(entries) == page_size:
        return entries, cursor + page_size
    thin = cursor + len(entries) < WIDEN_BELOW and len(words) > 1  # one word: the wider list is this list
    return entries, WIDER_CURSOR if thin else None


async def _topic_page(http: httpx.AsyncClient, query: str, start: int, page_size: int) -> list[dict]:
    params = {
        "search_query": query, "start": start, "max_results": page_size,
        "sortBy": "relevance", "sortOrder": "descending",
    }  # fmt: skip
    response = await http.get("/api/query", params=params)
    return _entries(response.raise_for_status())


def _entries(response: httpx.Response) -> list[dict]:
    try:
        feed = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise httpx.DecodingError(str(exc), request=response.request) from exc
    if feed.tag != f"{{{NS['atom']}}}feed":
        raise httpx.DecodingError("arXiv's answer is not an Atom feed", request=response.request)
    return [entry for node in feed.iterfind("atom:entry", NS) if (entry := _entry(node))]


def _entry(node: ET.Element) -> dict | None:
    match = _ABS_ID.search(node.findtext("atom:id", "", NS).strip())
    if not match:
        return None
    published = node.findtext("atom:published", "", NS)
    doi = node.findtext("arxiv:doi", "", NS).strip()
    return {
        "arxiv_id": match.group(1).lower(),
        "title": " ".join(node.findtext("atom:title", "", NS).split()),
        "authors": [
            joined
            for name in node.iterfind("atom:author/atom:name", NS)
            if (joined := " ".join((name.text or "").split()))
        ],
        "year": int(published[:4]) if published[:4].isdigit() else None,
        "doi": doi.lower() or None,
        "journal_ref": " ".join(node.findtext("arxiv:journal_ref", "", NS).split()) or None,
        "abstract": " ".join(node.findtext("atom:summary", "", NS).split()) or None,
    }
