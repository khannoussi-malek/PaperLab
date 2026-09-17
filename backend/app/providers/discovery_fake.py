"""Find papers and Similar without the network, for the E2E stack (DISCOVERY_PROVIDER=fake).

Three papers: one with a free PDF, one whose "PDF" link is a web page, and one with no free copy. They have DOIs under
the 10.5555 test prefix and no OpenAlex IDs, so adding one never collides with a real paper's OpenAlex ID.
OpenAlex, Crossref and Semantic Scholar answer all three. arXiv and CORE answer only the free paper: an arXiv ID would
give the closed paper a PDF link. Unpaywall lists the free and landing papers' links, so with OpenAlex off (the default,
and the E2E stack's setting) the badges match M19's. arxiv.org serves no PDF, so Add falls through to the fixture host.
"""

import json
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


def _handle(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    s2_papers = [_s2_paper(i, *paper) for i, paper in enumerate(PAPERS)]
    if host == "api.openalex.org" and path == "/works":
        return httpx.Response(200, json={"results": [_work(*paper) for paper in PAPERS]})
    if host == "api.openalex.org" and path.startswith("/works/"):
        return httpx.Response(200, json=_work(*PAPERS[0]))
    if host == "api.semanticscholar.org":
        if path.startswith("/recommendations/"):
            return httpx.Response(200, json={"recommendedPapers": s2_papers})
        if path == "/graph/v1/paper/search/match":
            return httpx.Response(200, json={"data": [{"paperId": "f" * 40}]})
        if path == "/graph/v1/paper/batch":
            return httpx.Response(200, json=[None] * len(json.loads(request.read())["ids"]))
        if path.startswith("/graph/v1/paper/"):
            return httpx.Response(200, json=s2_papers[0])
    if host == "api.crossref.org" and path == "/works":
        return httpx.Response(200, json={"message": {"items": [_crossref_item(*paper) for paper in PAPERS]}})
    if host == "api.crossref.org" and path.startswith("/works/"):
        return httpx.Response(200, json={"message": _crossref_item(*PAPERS[0])})
    if host == "export.arxiv.org" and path == "/api/query":
        return httpx.Response(200, text=_arxiv_feed(), headers={"content-type": "application/atom+xml"})
    if host == "api.core.ac.uk" and path == "/v3/search/works/":
        return httpx.Response(200, json={"results": [_core_work()]})
    if host == "api.unpaywall.org":
        pdf_url = next((url for _, doi, url in PAPERS if path == f"/v2/{doi}"), None)
        if pdf_url:
            return httpx.Response(200, json={"best_oa_location": {"url_for_pdf": pdf_url}, "oa_locations": []})
    if host == "pdf.paperlab.test" and path == "/paper.pdf":
        return httpx.Response(200, content=pdf_bytes(), headers={"content-type": "application/pdf"})
    if host == "pdf.paperlab.test" and path == "/page.html":
        return httpx.Response(200, text="<html><body>A landing page, not a PDF</body></html>")
    return httpx.Response(404, json={"error": f"the discovery fake has no {request.url}"})


def transport() -> httpx.MockTransport:
    return httpx.MockTransport(_handle)
