import httpx
import pytest
from conftest import FakeProvider

from app.providers import hal

pytestmark = pytest.mark.anyio

ONE_DOC = {
    "response": {
        "numFound": 1,
        "docs": [
            {
                "docid": "4020890",
                "title_s": ["The CRISPR-Cas9 System"],
                "abstract_s": ["A review of genome editing."],
                "authFullName_s": ["Nurul Husna Shafie", "Mohamed Saleem"],
                "doiId_s": "10.4172/1948-593X.1000109",
                "producedDate_s": "2014-11-07",
                "files_s": ["https://hal.science/hal-04020890/file/paper.pdf"],
            }
        ],
    }
}

TWO_DOCS_PAGE_1 = {"response": {"numFound": 2, "docs": [{"docid": "1", "title_s": ["Paper One"]}]}}
TWO_DOCS_PAGE_2 = {"response": {"numFound": 2, "docs": [{"docid": "2", "title_s": ["Paper Two"]}]}}

MALFORMED_QUERY_ERROR = {"error": {"msg": "Error. See help : /docs"}}


@pytest.fixture
async def hal_api():
    fake = FakeProvider()
    fake.client = hal.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_asks_for_structured_fields_and_sends_no_sort(hal_api):
    hal_api.reply("/search/", 200, json=ONE_DOC)

    [entry] = await hal.search(hal_api.client, "CRISPR", 10)

    request = hal_api.requests[0]
    assert "title_s" in request.url.params["fl"]
    assert "sort" not in request.url.params
    assert entry["title"] == "The CRISPR-Cas9 System"
    assert entry["abstract"] == "A review of genome editing."
    assert entry["doi"] == "10.4172/1948-593x.1000109"
    assert entry["authors"] == ["Nurul Husna Shafie", "Mohamed Saleem"]
    assert entry["year"] == 2014
    assert entry["pdf_url"] == "https://hal.science/hal-04020890/file/paper.pdf"


async def test_a_doc_with_no_abstract_doi_or_files_maps_without_them(hal_api):
    bare = {"response": {"numFound": 1, "docs": [{"docid": "1", "title_s": ["Bare"]}]}}
    hal_api.reply("/search/", 200, json=bare)

    [entry] = await hal.search(hal_api.client, "x", 1)

    assert entry == {
        "docid": "1", "title": "Bare", "authors": [], "year": None, "doi": None, "abstract": None,
        "pdf_url": None,
    }  # fmt: skip


async def test_get_finds_a_record_by_docid(hal_api):
    hal_api.reply("/search/", 200, json=ONE_DOC)

    entry = await hal.get(hal_api.client, "4020890")

    assert hal_api.requests[0].url.params["q"] == "docid:4020890"
    assert entry["docid"] == "4020890"


async def test_an_unknown_docid_is_none(hal_api):
    hal_api.reply("/search/", 200, json={"response": {"numFound": 0, "docs": []}})

    assert await hal.get(hal_api.client, "999999999") is None


async def test_search_page_advances_start_then_stops_at_numfound(hal_api):
    hal_api.reply("/search/", 200, json=TWO_DOCS_PAGE_1)
    entries_1, cursor_1 = await hal.search_page(hal_api.client, "x", 1, 0)

    hal_api.reply("/search/", 200, json=TWO_DOCS_PAGE_2)
    entries_2, cursor_2 = await hal.search_page(hal_api.client, "x", 1, cursor_1)

    assert [e["title"] for e in entries_1] == ["Paper One"]
    assert cursor_1 == 1
    assert [e["title"] for e in entries_2] == ["Paper Two"]
    assert cursor_2 is None


async def test_a_malformed_query_raises_an_httpx_error_not_keyerror(hal_api):
    """HAL answers a broken Solr query with HTTP 200 and a body-level error, not a 4xx status -- a plain
    raise_for_status() would miss this entirely."""
    hal_api.reply("/search/", 200, json=MALFORMED_QUERY_ERROR)

    with pytest.raises(httpx.HTTPError):
        await hal.search(hal_api.client, "(((unbalanced", 1)


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(hal_api, status, body):
    hal_api.reply("/search/", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await hal.search(hal_api.client, "x", 1)
