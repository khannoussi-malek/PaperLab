"""Find papers and Similar without the network, for the E2E stack (DISCOVERY_PROVIDER=fake).

Three papers: one with a free PDF, one whose "PDF" link is a web page, and one with no free copy. They have DOIs under
the 10.5555 test prefix and no OpenAlex IDs, so adding one never collides with a real paper's OpenAlex ID.
OpenAlex, Crossref and Semantic Scholar answer all three. arXiv and CORE answer only the free paper: an arXiv ID would
give the closed paper a PDF link. Unpaywall lists the free and landing papers' links, so with OpenAlex off (the default,
and the E2E stack's setting) the badges match M19's. arxiv.org serves no PDF, so Add falls through to the fixture host.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import httpx
import pymupdf

MAILTO = "e2e@paperlab.test"
PDF_HOST = "https://pdf.paperlab.test"
FREE_TITLE = "PaperLab Find Papers Fixture"
FREE_ARXIV_ID = "2609.00001"
LANDING_TITLE = "PaperLab Landing Page Fixture"
CLOSED_TITLE = "PaperLab Closed Access Fixture"
DOI_PREFIX = "10.5555/paperlab-e2e-"
PAPERS = [
    (FREE_TITLE, f"{DOI_PREFIX}free", f"{PDF_HOST}/paper.pdf"),
    (LANDING_TITLE, f"{DOI_PREFIX}landing", f"{PDF_HOST}/page.html"),
    (CLOSED_TITLE, f"{DOI_PREFIX}closed", None),
]
_BODY = "Finding papers starts from a title or an identifier. " * 12


@cache
def pdf_bytes() -> bytes:
    """One page: a bold 18pt title extraction takes as the paper's title, and enough prose to chunk."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), FREE_TITLE, fontsize=18, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(72, 100, 520, 400), _BODY, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _work(title: str, doi: str, pdf_url: str | None) -> dict:
    location = {"pdf_url": pdf_url, "landing_page_url": f"https://doi.org/{doi}"}
    return {
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "publication_year": 2026,
        "cited_by_count": 3,
        "authorships": [{"author": {"display_name": "Ada Fixture"}}],
        "primary_location": {"source": {"display_name": "Journal of Fixtures"}},
        "best_oa_location": location if pdf_url else None,
        "locations": [location],
    }


def _s2_paper(index: int, title: str, doi: str, pdf_url: str | None) -> dict:
    return {
        "paperId": f"{index + 1:040x}",
        "title": title,
        "year": 2026,
        "venue": "Journal of Fixtures",
        "authors": [{"name": "Ada Fixture"}],
        "externalIds": {"DOI": doi},
        "openAccessPdf": {"url": pdf_url or ""},
        "citationCount": 3,
    }


def _crossref_item(title: str, doi: str, pdf_url: str | None) -> dict:
    return {
        "DOI": doi,
        "type": "journal-article",
        "title": [title],
        "author": [{"given": "Ada", "family": "Fixture"}],
        "issued": {"date-parts": [[2026]]},
        "container-title": ["Journal of Fixtures"],
        "is-referenced-by-count": 3,
    }


def _arxiv_feed() -> str:
    title, doi, _ = PAPERS[0]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{FREE_ARXIV_ID}v1</id>
    <published>2026-01-05T00:00:00Z</published>
    <title>{title}</title>
    <author><name>Ada Fixture</name></author>
    <arxiv:doi>{doi}</arxiv:doi>
  </entry>
</feed>"""


def _core_work() -> dict:
    title, doi, pdf_url = PAPERS[0]
    return {"id": 900001, "title": title, "authors": [{"name": "Fixture, Ada"}], "yearPublished": 2026, "doi": doi,
            "arxivId": None, "downloadUrl": pdf_url}  # fmt: skip


# search_page() pagination (Task 11): a separate, small fixture list distinct from PAPERS, so a paginated search
# request never disturbs the single-page Find Papers / Similar / references fixtures above. Every provider's
# search_page() is exercised with page_size=2 against these 3 items, which exhausts on page 2 (a short page) for
# every next_cursor rule below, OpenAlex's 1-based `page` cursor included.
PAGE_PAPERS = [(f"PaperLab Pagination Fixture {n}", f"{DOI_PREFIX}page-{n}") for n in (1, 2, 3)]

# arXiv ids and S2 paperIds below are generated positionally, same as PAPERS' own (FREE_ARXIV_ID, _s2_paper(i, ...)
# via enumerate(PAPERS)). Offset by these bases so PAGE_PAPERS never lands on PAPERS' 2609.0000{1,2,3} / hex(1,2,3).
_PAGE_ARXIV_INDEX_BASE = 10_000
_PAGE_S2_INDEX_BASE = 1_000


def _page_slice(offset: int, limit: int) -> list[tuple[str, str]]:
    return PAGE_PAPERS[offset : offset + limit]


def _openalex_search_page(params: httpx.QueryParams) -> httpx.Response:
    page, page_size = int(params["page"]), int(params["per-page"])
    items = _page_slice((page - 1) * page_size, page_size)
    return httpx.Response(200, json={
        "meta": {"count": len(PAGE_PAPERS)}, "results": [_work(title, doi, None) for title, doi in items],
    })  # fmt: skip


def _crossref_search_page(params: httpx.QueryParams) -> httpx.Response:
    items = _page_slice(int(params["offset"]), int(params["rows"]))
    return httpx.Response(200, json={"message": {"items": [_crossref_item(title, doi, None) for title, doi in items]}})


def _arxiv_search_page_feed(params: httpx.QueryParams) -> str:
    offset, page_size = int(params["start"]), int(params["max_results"])
    entries = "".join(
        f"""
  <entry>
    <id>http://arxiv.org/abs/2609.{index:05d}v1</id>
    <published>2026-01-05T00:00:00Z</published>
    <title>{title}</title>
    <author><name>Ada Fixture</name></author>
    <arxiv:doi>{doi}</arxiv:doi>
  </entry>"""
        for index, (title, doi) in enumerate(_page_slice(offset, page_size), start=_PAGE_ARXIV_INDEX_BASE + offset + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">{entries}
</feed>"""


def _page_core_work(core_id: int, title: str, doi: str) -> dict:
    return {"id": core_id, "title": title, "authors": [{"name": "Fixture, Ada"}], "yearPublished": 2026, "doi": doi,
            "arxivId": None, "downloadUrl": None}  # fmt: skip


def _core_search_page(params: httpx.QueryParams) -> httpx.Response:
    offset, page_size = int(params["offset"]), int(params["limit"])
    results = [
        _page_core_work(900100 + offset + i, title, doi)
        for i, (title, doi) in enumerate(_page_slice(offset, page_size))
    ]
    return httpx.Response(200, json={"totalHits": len(PAGE_PAPERS), "results": results})


def _s2_search_page(params: httpx.QueryParams) -> httpx.Response:
    offset, page_size = int(params["offset"]), int(params["limit"])
    items = _page_slice(offset, page_size)
    data = [_s2_paper(_PAGE_S2_INDEX_BASE + offset + i, title, doi, None) for i, (title, doi) in enumerate(items)]
    body = {"data": data}
    if offset + page_size < len(PAGE_PAPERS):
        body["next"] = offset + page_size
    return httpx.Response(200, json=body)


@dataclass(frozen=True)
class FakeAdapter:
    """One source's fake: `host` plus a `match(path, params)` predicate decide whether this adapter answers a
    request; `handle` builds the response. `_handle` below is pure dispatch over a list of these."""

    host: str
    match: Callable[[str, httpx.QueryParams], bool]
    handle: Callable[[httpx.Request], httpx.Response]


def _openalex_handle(request: httpx.Request) -> httpx.Response:
    if "page" in request.url.params:
        return _openalex_search_page(request.url.params)
    if request.url.path.startswith("/works/"):
        return httpx.Response(200, json=_work(*PAPERS[0]))
    return httpx.Response(200, json={"results": [_work(*paper) for paper in PAPERS]})


def _s2_handle(request: httpx.Request) -> httpx.Response:
    s2_papers = [_s2_paper(i, *paper) for i, paper in enumerate(PAPERS)]
    path = request.url.path
    if path.endswith("/references"):
        return httpx.Response(200, json={"offset": 0, "data": [{"citedPaper": p} for p in s2_papers]})
    if path.endswith("/citations"):
        return httpx.Response(200, json={"offset": 0, "data": [{"citingPaper": s2_papers[0]}]})
    if path.startswith("/recommendations/"):
        return httpx.Response(200, json={"recommendedPapers": s2_papers})
    if path == "/graph/v1/paper/search/match":
        return httpx.Response(200, json={"data": [{"paperId": "f" * 40}]})
    if path == "/graph/v1/paper/search":
        return _s2_search_page(request.url.params)
    if path == "/graph/v1/paper/batch":
        return httpx.Response(200, json=[None] * len(json.loads(request.read())["ids"]))
    return httpx.Response(200, json=s2_papers[0])


def _crossref_handle(request: httpx.Request) -> httpx.Response:
    if "offset" in request.url.params:
        return _crossref_search_page(request.url.params)
    if request.url.path.startswith("/works/"):
        return httpx.Response(200, json={"message": _crossref_item(*PAPERS[0])})
    return httpx.Response(200, json={"message": {"items": [_crossref_item(*paper) for paper in PAPERS]}})


def _arxiv_handle(request: httpx.Request) -> httpx.Response:
    if "start" in request.url.params:
        return httpx.Response(
            200, text=_arxiv_search_page_feed(request.url.params), headers={"content-type": "application/atom+xml"}
        )
    return httpx.Response(200, text=_arxiv_feed(), headers={"content-type": "application/atom+xml"})


def _core_handle(request: httpx.Request) -> httpx.Response:
    if "offset" in request.url.params:
        return _core_search_page(request.url.params)
    return httpx.Response(200, json={"results": [_core_work()]})


def _unpaywall_handle(request: httpx.Request) -> httpx.Response:
    pdf_url = next((url for _, doi, url in PAPERS if request.url.path == f"/v2/{doi}"), None)
    if pdf_url:
        return httpx.Response(200, json={"best_oa_location": {"url_for_pdf": pdf_url}, "oa_locations": []})
    return httpx.Response(404, json={"error": f"the discovery fake has no {request.url}"})


def _pdf_handle(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/paper.pdf":
        return httpx.Response(200, content=pdf_bytes(), headers={"content-type": "application/pdf"})
    return httpx.Response(200, text="<html><body>A landing page, not a PDF</body></html>")


ADAPTERS: tuple[FakeAdapter, ...] = (
    FakeAdapter(
        "api.openalex.org",
        lambda path, params: path == "/works" or path.startswith("/works/"),
        _openalex_handle,
    ),
    FakeAdapter("api.semanticscholar.org", lambda path, params: True, _s2_handle),
    FakeAdapter(
        "api.crossref.org",
        lambda path, params: path == "/works" or path.startswith("/works/"),
        _crossref_handle,
    ),
    FakeAdapter("export.arxiv.org", lambda path, params: path == "/api/query", _arxiv_handle),
    FakeAdapter("api.core.ac.uk", lambda path, params: path == "/v3/search/works/", _core_handle),
    FakeAdapter("api.unpaywall.org", lambda path, params: True, _unpaywall_handle),
    FakeAdapter("pdf.paperlab.test", lambda path, params: True, _pdf_handle),
)  # fmt: skip


def _handle(request: httpx.Request) -> httpx.Response:
    for adapter in ADAPTERS:
        if request.url.host == adapter.host and adapter.match(request.url.path, request.url.params):
            return adapter.handle(request)
    return httpx.Response(404, json={"error": f"the discovery fake has no {request.url}"})


def transport() -> httpx.MockTransport:
    return httpx.MockTransport(_handle)
