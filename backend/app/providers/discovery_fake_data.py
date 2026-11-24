"""The papers the fake sources know, and the paging every fake source shares."""

from functools import cache

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
SECOND_HOP_TITLE = (
    "PaperLab Second Hop Fixture"  # cites only the closed paper, so it is two hops from a pagination seed
)
SECOND_HOP_DOI = f"{DOI_PREFIX}hop2"
THIRD_HOP_TITLE = "PaperLab Third Hop Fixture"  # cited by the second-hop paper only
THIRD_HOP_DOI = f"{DOI_PREFIX}hop3"
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
