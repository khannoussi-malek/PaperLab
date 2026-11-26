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
    assert landing_page.identify(page(("citation_title", "  A &amp; B\n  rest "))) == "A & B rest"
    assert landing_page.identify(page(("og:title", "Nature"), attr="property")) is None, (
        "a site's title isn't a paper's"
    )
    assert landing_page.identify(page(("description", "nothing useful"))) is None


def test_only_links_count():
    assert landing_page.is_link(f"  {NATURE} ")
    assert not landing_page.is_link("protein structure prediction")


async def test_only_public_web_pages_are_read_whatever_the_address_looks_like(monkeypatch):
    inside = {"localhost": ["127.0.0.1"], "2130706433": ["127.0.0.1"], "intranet.example.org": ["10.0.0.5"]}

    async def resolve(host: str) -> list[str]:  # DNS, faked as it answers these
        return inside.get(host, ["93.184.216.34"])

    monkeypatch.setattr("app.core.papers.pdf_links.resolve_host", resolve)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="x"))) as http:
        for url in ("file:///etc/passwd", "http://localhost:8000/api", "http://127.0.0.1/", "http://[::1]/",
                    "http://2130706433/", "http://intranet.example.org/paper"):  # fmt: skip
            with pytest.raises(landing_page.PageUnreadable, match="only public web pages"):
                await landing_page.read(http, url)


async def test_a_redirect_into_the_private_network_is_refused_by_the_clients_guard(monkeypatch):
    async def resolve(host: str) -> list[str]:
        return ["10.0.0.5"] if host == "inside.example.org" else ["93.184.216.34"]

    monkeypatch.setattr("app.core.papers.pdf_links.resolve_host", resolve)

    def site(request: httpx.Request) -> httpx.Response:
        if request.url.host == "journal.example.org":
            return httpx.Response(302, headers={"Location": "http://inside.example.org/admin"})
        return httpx.Response(200, text="secrets")

    from app.core.papers.pdf_links import guard

    transport = httpx.MockTransport(site)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True, event_hooks={"request": [guard]}) as http:
        with pytest.raises(landing_page.PageUnreadable, match="only public web pages"):
            await landing_page.read(http, "https://journal.example.org/paper")


def test_a_page_in_latin_1_is_read_by_its_own_charset():
    body = '<meta charset="iso-8859-1"><meta name="citation_title" content="Caf\xe9 effects">'.encode("latin-1")
    assert landing_page.identify(landing_page._decode(body, None)) == "Café effects"


async def test_a_page_is_read_up_to_its_size_cap_and_a_refusal_says_why():
    big = "x" * (landing_page.MAX_BYTES + 10)

    def site(request: httpx.Request) -> httpx.Response:
        return {"/big": httpx.Response(200, text=big), "/gone": httpx.Response(403, text="no bots")}[request.url.path]

    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http:
        assert len(await landing_page.read(http, "https://example.org/big")) == landing_page.MAX_BYTES
        with pytest.raises(landing_page.PageUnreadable, match="answered 403"):
            await landing_page.read(http, "https://example.org/gone")


async def test_a_link_without_a_doi_is_searched_by_the_doi_its_page_gives(session, discovery_fakes):
    discovery_fakes.pdf_host.reply("/science/article/pii/S0004370221000862", 200, text=page(("citation_doi", DOI)))
    discovery_fakes.openalex.route(f"/works/doi:{DOI}", httpx.Response(404, text="<!doctype html>"))
    discovery_fakes.crossref.reply(f"/works/{DOI}", 200, json={"message": {"DOI": DOI, "type": "journal-article",
        "title": [TITLE], "author": [{"given": "John", "family": "Jumper"}]}})  # fmt: skip
    discovery_fakes.s2.reply("/graph/v1/paper/batch", 200, json=[None])

    link = "https://www.sciencedirect.com/science/article/pii/S0004370221000862"
    [result] = (await discovery.search(session, discovery_fakes.turned_on("crossref"), link)).results

    assert (result.doi, result.title) == (DOI, TITLE)
    assert len(discovery_fakes.pdf_host.requests) == 1, "its page was read"


async def test_a_page_that_cannot_be_read_or_says_nothing_is_a_conflict_in_words(session, discovery_fakes):
    discovery_fakes.pdf_host.reply("/document/1", 403, text="Forbidden")
    discovery_fakes.pdf_host.reply("/blank", 200, text=page())
    with pytest.raises(Conflict, match="Couldn't read that page"):
        await discovery.search(session, discovery_fakes.providers, "https://ieeexplore.ieee.org/document/1")
    with pytest.raises(Conflict, match="doesn't say which paper"):
        await discovery.search(session, discovery_fakes.providers, "https://example.org/blank")


def test_a_nature_link_spells_its_doi_and_other_links_dont():
    assert landing_page.doi_from_link(NATURE) == DOI
    assert landing_page.doi_from_link("https://www.nature.com/articles/nature14539") == "10.1038/nature14539"
    assert landing_page.doi_from_link("https://ieeexplore.ieee.org/document/1") is None
    assert landing_page.doi_from_link("https://www.nature.com/articles/nature14539.pdf") == "10.1038/nature14539"
    assert landing_page.doi_from_link(f"{NATURE}?error=cookies_not_supported") == DOI
    assert landing_page.doi_from_link("https://www.nature.com/articles/subjects/biology") is None, "not an article"


def test_a_bot_check_is_known_by_its_whole_title_not_an_article_that_mentions_one():
    assert landing_page.is_bot_check("<title>Just a moment...</title>")
    assert landing_page.is_bot_check("<title>Access Denied | Example</title>")
    assert not landing_page.is_bot_check("<title>Access denied: barriers to care in rural clinics</title>")


async def test_a_nature_link_is_searched_by_its_doi_without_reading_the_page(session, discovery_fakes):
    discovery_fakes.openalex.route(f"/works/doi:{DOI}", httpx.Response(404, text="<!doctype html>"))
    discovery_fakes.crossref.reply(f"/works/{DOI}", 200, json={"message": {"DOI": DOI, "type": "journal-article",
        "title": [TITLE], "author": [{"given": "John", "family": "Jumper"}]}})  # fmt: skip
    discovery_fakes.s2.reply("/graph/v1/paper/batch", 200, json=[None])

    [result] = (await discovery.search(session, discovery_fakes.turned_on("crossref"), NATURE)).results

    assert result.doi == DOI
    assert discovery_fakes.pdf_host.requests == [], "the page wasn't read"


async def test_a_bot_check_instead_of_the_page_says_the_site_turns_readers_away(session, discovery_fakes):
    challenge = "<html><head><title>Client Challenge</title></head><body>Loading…</body></html>"
    discovery_fakes.pdf_host.reply("/document/9156610", 200, text=challenge)
    with pytest.raises(Conflict, match="turns automatic readers away"):
        await discovery.search(session, discovery_fakes.providers, "https://ieeexplore.ieee.org/document/9156610")


async def test_a_bot_check_sent_as_a_403_says_the_site_turns_readers_away(session, discovery_fakes):
    challenge = "<html><head><title>Just a moment...</title></head><body>Checking your browser…</body></html>"
    discovery_fakes.pdf_host.reply("/science/article/pii/S1", 403, text=challenge)
    with pytest.raises(Conflict, match="turns automatic readers away"):
        await discovery.search(
            session, discovery_fakes.providers, "https://www.sciencedirect.com/science/article/pii/S1"
        )
