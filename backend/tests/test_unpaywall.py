import httpx
import pytest
from conftest import FakeProvider, recorded_discovery

from app.providers import unpaywall

pytestmark = pytest.mark.anyio

EMAIL = "unpaywall_01@example.com"
NUMPY_DOI = "10.1038/s41586-020-2649-2"


@pytest.fixture
async def unpaywall_api():
    fake = FakeProvider()
    fake.client = unpaywall.new_client(EMAIL, transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_pdf_urls_are_the_best_location_then_every_location_in_order(unpaywall_api):
    unpaywall_api.reply(f"/v2/{NUMPY_DOI}", 200, json=recorded_discovery("unpaywall_numpy"))

    urls = await unpaywall.pdf_urls(unpaywall_api.client, NUMPY_DOI)

    assert urls == [
        "https://www.nature.com/articles/s41586-020-2649-2.pdf",
        "https://arxiv.org/pdf/2006.10256",
    ]
    assert unpaywall_api.requests[0].url.params["email"] == EMAIL


async def test_a_paper_with_only_landing_pages_has_no_pdf_urls(unpaywall_api):
    unpaywall_api.reply("/v2/10.18653/v1/n19-1423", 200, json=recorded_discovery("unpaywall_bert"))

    assert await unpaywall.pdf_urls(unpaywall_api.client, "10.18653/v1/n19-1423") == []


async def test_duplicates_nulls_and_non_web_links_are_left_out(unpaywall_api):
    record = {
        "best_oa_location": {"url_for_pdf": "https://repo.example/a.pdf"},
        "oa_locations": [
            {"url_for_pdf": "https://repo.example/a.pdf"},
            {"url_for_pdf": None},
            {"url_for_pdf": "ftp://files.example/b.pdf"},
            {"url_for_pdf": "http://mirror.example/c.pdf"},
        ],
    }
    unpaywall_api.reply(f"/v2/{NUMPY_DOI}", 200, json=record)

    assert await unpaywall.pdf_urls(unpaywall_api.client, NUMPY_DOI) == [
        "https://repo.example/a.pdf",
        "http://mirror.example/c.pdf",
    ]


async def test_a_closed_paper_has_no_pdf_urls(unpaywall_api):
    unpaywall_api.reply(f"/v2/{NUMPY_DOI}", 200, json={"best_oa_location": None, "oa_locations": []})

    assert await unpaywall.pdf_urls(unpaywall_api.client, NUMPY_DOI) == []


async def test_a_doi_unpaywall_does_not_have_has_no_pdf_urls(unpaywall_api):
    # Unpaywall's 404 body is an HTML page.
    unpaywall_api.reply("/v2/10.9999/not-in-unpaywall", 404, text="<!doctype html><title>404 Not Found</title>")

    assert await unpaywall.pdf_urls(unpaywall_api.client, "10.9999/not-in-unpaywall") == []


@pytest.mark.parametrize(
    ("status", "reply"),
    [
        (422, {"json": {"error": True, "message": "Email address required in API call"}}),
        (503, {"text": "busy"}),
        (200, {"text": "<!doctype html>"}),
    ],
    ids=["email refused", "server error", "malformed body"],
)
async def test_failures_raise_an_httpx_error(unpaywall_api, status, reply):
    unpaywall_api.reply(f"/v2/{NUMPY_DOI}", status, **reply)

    with pytest.raises(httpx.HTTPError):
        await unpaywall.pdf_urls(unpaywall_api.client, NUMPY_DOI)
