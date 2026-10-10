import httpx
import pytest
from conftest import FakeProvider

from app.providers import doaj

pytestmark = pytest.mark.anyio

ONE_ARTICLE = {
    "total": 1,
    "page": 1,
    "pageSize": 10,
    "results": [
        {
            "id": "000122f776cb4f27b0f575971a4bed38",
            "bibjson": {
                "title": "A feature selection scheme for machine learning",
                "abstract": "Selection of important features is vital.",
                "year": "2025",
                "author": [{"name": "Philemon Uten Emmoh"}],
                "identifier": [
                    {"id": "10.46481/jnsps.2025.2273", "type": "doi"},
                    {"id": "2714-2817", "type": "pissn"},
                ],
                "link": [
                    {"content_type": "pdf", "type": "fulltext", "url": "https://example.org/paper.pdf"},
                    {"content_type": "HTML", "type": "fulltext", "url": "https://example.org/landing"},
                ],
            },
        }
    ],
}

TWO_PAGE_1 = {
    "total": 2, "page": 1, "pageSize": 1,
    "results": [{"id": "1" * 32, "bibjson": {"title": "One"}}],
    "next": "https://doaj.org/api/v4/search/articles/x?page=2&pageSize=1",
}
TWO_PAGE_2 = {"total": 2, "page": 2, "pageSize": 1, "results": [{"id": "2" * 32, "bibjson": {"title": "Two"}}]}


@pytest.fixture
async def doaj_api():
    fake = FakeProvider()
    fake.client = doaj.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_returns_doajs_own_bibjson_records(doaj_api):
    doaj_api.reply('/api/search/articles/title:"machine learning"', 200, json=ONE_ARTICLE)

    [article] = await doaj.search(doaj_api.client, "machine learning", 10)

    assert article["id"] == "000122f776cb4f27b0f575971a4bed38"
    assert article["bibjson"]["title"] == "A feature selection scheme for machine learning"


async def test_search_clamps_the_page_size_to_doajs_own_cap(doaj_api):
    doaj_api.reply('/api/search/articles/title:"x"', 200, json={"total": 0, "page": 1, "pageSize": 100, "results": []})

    await doaj.search(doaj_api.client, "x", 1000)

    assert doaj_api.requests[0].url.params["pageSize"] == "100"


async def test_get_finds_an_article_by_id(doaj_api):
    doaj_api.reply(f"/api/articles/{'0' * 32}", 200, json={"id": "0" * 32, "bibjson": {"title": "Bare"}})

    article = await doaj.get(doaj_api.client, "0" * 32)

    assert article["bibjson"]["title"] == "Bare"


async def test_an_unknown_article_id_is_none(doaj_api):
    doaj_api.reply(f"/api/articles/{'9' * 32}", 404, json={"status": "not_found"})

    assert await doaj.get(doaj_api.client, "9" * 32) is None


async def test_search_page_follows_the_next_key_then_stops(doaj_api):
    doaj_api.reply('/api/search/articles/title:"x"', 200, json=TWO_PAGE_1)
    entries_1, cursor_1 = await doaj.search_page(doaj_api.client, "x", 1, 1)

    doaj_api.reply('/api/search/articles/title:"x"', 200, json=TWO_PAGE_2)
    entries_2, cursor_2 = await doaj.search_page(doaj_api.client, "x", 1, cursor_1)

    assert [e["id"] for e in entries_1] == ["1" * 32]
    assert cursor_1 == 2
    assert [e["id"] for e in entries_2] == ["2" * 32]
    assert cursor_2 is None


async def test_search_page_stops_at_the_hard_result_cap_even_if_next_is_present(doaj_api):
    body = {"total": 50000, "page": 10, "results": [{"id": "1" * 32}], "next": "https://doaj.org/api/v4/x?page=11"}
    doaj_api.reply('/api/search/articles/title:"x"', 200, json=body)

    _, next_cursor = await doaj.search_page(doaj_api.client, "x", 100, 10)

    assert next_cursor is None  # page 10 at page_size 100 = 1000 results already reached; "next" is ignored


async def test_search_quotes_a_reserved_term_so_it_does_not_hang(doaj_api):
    # Sent bare, a reserved Elasticsearch term like "AND" hangs until this module's own 10s timeout
    # (confirmed live); registering the reply at the quoted path and getting a routed response at all
    # (FakeProvider raises AssertionError on an unrouted request) is the proof the term was quoted.
    doaj_api.reply('/api/search/articles/title:"AND"', 200, json={"total": 0, "page": 1, "results": []})

    results = await doaj.search(doaj_api.client, "AND", 1)

    assert results == []


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(doaj_api, status, body):
    doaj_api.reply('/api/search/articles/title:"x"', status, text=body)

    with pytest.raises(httpx.HTTPError):
        await doaj.search(doaj_api.client, "x", 1)
