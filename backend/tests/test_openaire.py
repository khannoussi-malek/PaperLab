import httpx
import pytest
from conftest import FakeProvider

from app.providers import openaire

pytestmark = pytest.mark.anyio

ONE_RECORD = {
    "header": {"numFound": 1, "page": 1, "pageSize": 10},
    "results": [
        {
            "id": "openaire____::ad7636681cefebfbde101792892e3c1a",
            "type": "publication",
            "mainTitle": "CRISPR gene editing in enzyme development",
            "descriptions": ["An overview of CRISPR applications."],
            "pids": [{"scheme": "doi", "value": "10.1016/j.enzmictec.2025.110799"}],
            "authors": [{"fullName": "Youmin Zhu"}],
            "publicationDate": "2026-04-01",
            "instances": [{"urls": ["https://doi.org/10.1016/j.enzmictec.2025.110799"]}],
        }
    ],
}

TWO_PAGE_1 = {
    "header": {"numFound": 2, "page": 1, "pageSize": 1},
    "results": [{"id": "x" * 32, "type": "publication", "mainTitle": "One"}],
}
TWO_PAGE_2 = {
    "header": {"numFound": 2, "page": 2, "pageSize": 1},
    "results": [{"id": "y" * 32, "type": "publication", "mainTitle": "Two"}],
}


@pytest.fixture
async def openaire_api():
    fake = FakeProvider()
    fake.client = openaire.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_filters_to_publication_type(openaire_api):
    openaire_api.reply("/graph/v3/research-products", 200, json=ONE_RECORD)

    [record] = await openaire.search(openaire_api.client, "CRISPR", 10)

    request = openaire_api.requests[0]
    assert request.url.params["type"] == "publication"
    assert record["mainTitle"] == "CRISPR gene editing in enzyme development"


async def test_get_finds_a_record_by_id(openaire_api):
    openaire_api.reply(f"/graph/v3/research-products/{'0' * 32}", 200, json={"id": "0" * 32, "mainTitle": "Bare"})

    record = await openaire.get(openaire_api.client, "0" * 32)

    assert record["mainTitle"] == "Bare"


async def test_an_unknown_record_id_is_none(openaire_api):
    openaire_api.reply(f"/graph/v3/research-products/{'9' * 32}", 404, json={"error": "Not Found"})

    assert await openaire.get(openaire_api.client, "9" * 32) is None


async def test_search_page_advances_the_page_number_then_stops(openaire_api):
    openaire_api.reply("/graph/v3/research-products", 200, json=TWO_PAGE_1)
    entries_1, cursor_1 = await openaire.search_page(openaire_api.client, "x", 1, 1)

    openaire_api.reply("/graph/v3/research-products", 200, json=TWO_PAGE_2)
    entries_2, cursor_2 = await openaire.search_page(openaire_api.client, "x", 1, cursor_1)

    assert [e["id"] for e in entries_1] == ["x" * 32]
    assert cursor_1 == 2
    assert [e["id"] for e in entries_2] == ["y" * 32]
    assert cursor_2 is None


async def test_search_page_stops_at_the_hard_result_cap_even_if_more_remain(openaire_api):
    body = {"header": {"numFound": 50000, "page": 500, "pageSize": 20}, "results": [{"id": "x" * 32}]}
    openaire_api.reply("/graph/v3/research-products", 200, json=body)

    _, next_cursor = await openaire.search_page(openaire_api.client, "x", 20, 500)

    assert next_cursor is None  # page 500 at page_size 20 = 10000 results already reached; real numFound is ignored


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(openaire_api, status, body):
    openaire_api.reply("/graph/v3/research-products", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await openaire.search(openaire_api.client, "x", 1)
