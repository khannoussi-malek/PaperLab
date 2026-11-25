"""A paper's page read for what identifies it, when its link holds no DOI (Nature, IEEE Xplore, ScienceDirect)."""

import httpx
import pytest

from app.core.search import discovery, landing_page
from app.domain.errors import Conflict

pytestmark = pytest.mark.anyio

NATURE = "https://www.nature.com/articles/s41586-021-03819-2"
DOI = "10.1038/s41586-021-03819-2"
TITLE = "Highly accurate protein structure prediction with AlphaFold"


def page(*metas: tuple[str, str], attr: str = "name") -> str:
    tags = "".join(f'<meta {attr}="{name}" content="{content}">' for name, content in metas)
    return f"<!doctype html><html><head><title>x</title>{tags}</head><body>…</body></html>"


def test_a_page_is_known_by_its_doi_first_then_its_arxiv_id_then_its_title():
    assert landing_page.identify(page(("citation_title", TITLE), ("citation_doi", f"doi:{DOI}"))) == DOI
    assert landing_page.identify(page(("dc.identifier", f"https://doi.org/{DOI}."))) == DOI
    assert landing_page.identify(page(("citation_arxiv_id", "1810.04805"))) == "arXiv:1810.04805"
    assert landing_page.identify(page(("og:title", "  A &amp; B\n  rest "), attr="property")) == "A & B rest"
    assert landing_page.identify(page(("description", "nothing useful"))) is None


def test_only_links_count_and_only_public_web_pages_are_read():
    assert landing_page.is_link(f"  {NATURE} ")
    assert not landing_page.is_link("protein structure prediction")
    for url in (
        "file:///etc/passwd",
        "http://localhost:8000/api",
        "http://127.0.0.1/",
        "http://10.0.0.5/x",
        "http://printer.local/",
        "http://[::1]/",
    ):
        assert not landing_page._public(url), url
    assert landing_page._public(NATURE) and landing_page._public("http://93.184.216.34/paper")


async def test_a_page_is_read_up_to_its_size_cap_and_a_refusal_says_why():
    big = "x" * (landing_page.MAX_BYTES + 10)

    def site(request: httpx.Request) -> httpx.Response:
        return {"/big": httpx.Response(200, text=big), "/gone": httpx.Response(403, text="no bots")}[request.url.path]

    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http:
        assert len(await landing_page.read(http, "https://example.org/big")) == landing_page.MAX_BYTES
        with pytest.raises(landing_page.PageUnreadable, match="answered 403"):
            await landing_page.read(http, "https://example.org/gone")
        with pytest.raises(landing_page.PageUnreadable, match="only public web pages"):
            await landing_page.read(http, "http://localhost/x")


async def test_a_link_without_a_doi_is_searched_by_the_doi_its_page_gives(session, discovery_fakes):
    discovery_fakes.pdf_host.reply("/articles/s41586-021-03819-2", 200, text=page(("citation_doi", DOI)))
    discovery_fakes.openalex.route(f"/works/doi:{DOI}", httpx.Response(404, text="<!doctype html>"))
    discovery_fakes.crossref.reply(f"/works/{DOI}", 200, json={"message": {"DOI": DOI, "type": "journal-article",
        "title": [TITLE], "author": [{"given": "John", "family": "Jumper"}]}})  # fmt: skip
    discovery_fakes.s2.reply("/graph/v1/paper/batch", 200, json=[None])

    [result] = (await discovery.search(session, discovery_fakes.turned_on("crossref"), NATURE)).results

    assert (result.doi, result.title) == (DOI, TITLE)


async def test_a_page_that_cannot_be_read_or_says_nothing_is_a_conflict_in_words(session, discovery_fakes):
    discovery_fakes.pdf_host.reply("/document/1", 403, text="Forbidden")
    discovery_fakes.pdf_host.reply("/blank", 200, text=page())
    with pytest.raises(Conflict, match="Couldn't read that page"):
        await discovery.search(session, discovery_fakes.providers, "https://ieeexplore.ieee.org/document/1")
    with pytest.raises(Conflict, match="doesn't say which paper"):
        await discovery.search(session, discovery_fakes.providers, "https://example.org/blank")
