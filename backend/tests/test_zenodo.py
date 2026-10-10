import httpx
import pytest
from conftest import FakeProvider

from app.providers import zenodo

pytestmark = pytest.mark.anyio

ONE_RECORD = {
    "hits": {
        "hits": [
            {
                "id": 22132605,
                "doi": "10.5281/ZENODO.22132605",
                "metadata": {
                    "title": "CRISPR Based <i>Gene</i> Editing",
                    "creators": [{"name": "Dar, Shehneela"}],
                    "publication_date": "2026-08-27",
                    "description": "<p>An overview of <strong>CRISPR</strong> applications.</p>",
                },
                "files": [
                    {"key": "paper.pdf", "links": {"self": "https://zenodo.org/api/records/22132605/files/paper.pdf/content"}},
                    {"key": "data.csv", "links": {"self": "https://zenodo.org/api/records/22132605/files/data.csv/content"}},
                ],
            }
        ]
    }
}

TWO_RECORDS_PAGE_1 = {
    "hits": {"hits": [{"id": 1, "metadata": {"title": "Paper One"}}]},
    "links": {"next": "https://zenodo.org/api/records?page=2"},
}
TWO_RECORDS_PAGE_2 = {"hits": {"hits": [{"id": 2, "metadata": {"title": "Paper Two"}}]}, "links": {}}


@pytest.fixture
async def zenodo_api():
    fake = FakeProvider()
    fake.client = zenodo.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_filters_to_publication_article_and_cleans_markup(zenodo_api):
    zenodo_api.reply("/api/records", 200, json=ONE_RECORD)

    [entry] = await zenodo.search(zenodo_api.client, "CRISPR", 10)

    request = zenodo_api.requests[0]
    assert request.url.params["type"] == "publication"
    assert request.url.params["subtype"] == "article"
    assert "sort" not in request.url.params
    assert entry["title"] == "CRISPR Based Gene Editing"
    assert entry["abstract"] == "An overview of CRISPR applications."
    assert entry["doi"] == "10.5281/zenodo.22132605"
    assert entry["authors"] == ["Dar, Shehneela"]
    assert entry["year"] == 2026


async def test_search_picks_the_pdf_file_and_ignores_other_file_types(zenodo_api):
    zenodo_api.reply("/api/records", 200, json=ONE_RECORD)

    [entry] = await zenodo.search(zenodo_api.client, "CRISPR", 10)

    assert entry["pdf_url"] == "https://zenodo.org/api/records/22132605/files/paper.pdf/content"


async def test_search_clamps_the_page_size_to_the_anonymous_cap(zenodo_api):
    zenodo_api.reply("/api/records", 200, json={"hits": {"hits": []}})

    await zenodo.search(zenodo_api.client, "x", 1000)

    assert zenodo_api.requests[0].url.params["size"] == "25"


async def test_a_record_with_no_files_doi_or_description_maps_without_them(zenodo_api):
    bare = {"hits": {"hits": [{"id": 5, "metadata": {"title": "Bare"}}]}}
    zenodo_api.reply("/api/records", 200, json=bare)

    [entry] = await zenodo.search(zenodo_api.client, "x", 1)

    assert entry == {
        "id": "5", "title": "Bare", "authors": [], "year": None, "doi": None, "abstract": None, "pdf_url": None,
    }  # fmt: skip


async def test_a_malformed_200_body_raises_an_httpx_error_not_a_bare_json_error(zenodo_api):
    zenodo_api.reply("/api/records", 200, text="<html>not json</html>")

    with pytest.raises(httpx.HTTPError):
        await zenodo.search(zenodo_api.client, "x", 1)


async def test_get_parses_a_single_record(zenodo_api):
    zenodo_api.reply("/api/records/22132605", 200, json=ONE_RECORD["hits"]["hits"][0])

    entry = await zenodo.get(zenodo_api.client, "22132605")

    assert entry["id"] == "22132605"
    assert entry["title"] == "CRISPR Based Gene Editing"


async def test_an_unknown_record_id_is_none(zenodo_api):
    zenodo_api.reply("/api/records/999999999999", 404, json={"status": 404, "message": "not found"})

    assert await zenodo.get(zenodo_api.client, "999999999999") is None


async def test_search_page_follows_links_next_then_stops(zenodo_api):
    zenodo_api.reply("/api/records", 200, json=TWO_RECORDS_PAGE_1)
    entries_1, cursor_1 = await zenodo.search_page(zenodo_api.client, "x", 1, 1)

    zenodo_api.reply("/api/records", 200, json=TWO_RECORDS_PAGE_2)
    entries_2, cursor_2 = await zenodo.search_page(zenodo_api.client, "x", 1, cursor_1)

    assert [e["title"] for e in entries_1] == ["Paper One"]
    assert cursor_1 == 2
    assert [e["title"] for e in entries_2] == ["Paper Two"]
    assert cursor_2 is None


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(zenodo_api, status, body):
    zenodo_api.reply("/api/records", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await zenodo.search(zenodo_api.client, "x", 1)
