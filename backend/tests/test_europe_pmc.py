import httpx
import pytest
from conftest import FakeProvider

from app.providers import europe_pmc

pytestmark = pytest.mark.anyio

ONE_RESULT = {
    "hitCount": 1,
    "resultList": {
        "result": [
            {
                "id": "42428244", "source": "MED", "pmid": "42428244", "pmcid": "PMC13346171",
                "doi": "10.3389/fgeed.2026.1844919",
                "title": "The application of CRISPR gene-editing technology in the <i>in vivo</i> delivery.",
                "authorList": {"author": [{"fullName": "Zhang X"}, {"fullName": "Shi H"}]},
                "pubYear": "2026",
                "abstractText": "CRISPR enables <i>in vivo</i> gene editing.",
                "citedByCount": 3,
            }
        ]
    },
}

TWO_RESULTS_PAGE_1 = {
    "hitCount": 2,
    "nextCursorMark": "AoIIQDaIlCg1NjQ3MDk5NA==",
    "resultList": {"result": [{"id": "1", "title": "Paper One", "pubYear": "2024"}]},
}
TWO_RESULTS_PAGE_2 = {
    "hitCount": 2,
    "resultList": {"result": [{"id": "2", "title": "Paper Two", "pubYear": "2024"}]},
}

ZERO_RESULTS = {"hitCount": 0, "resultList": {"result": []}}


@pytest.fixture
async def epmc_api():
    fake = FakeProvider()
    fake.client = europe_pmc.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_asks_for_relevance_sort_and_core_result_type(epmc_api):
    epmc_api.reply("/europepmc/webservices/rest/search", 200, json=ZERO_RESULTS)

    await europe_pmc.search(epmc_api.client, "gene editing", 10)

    request = epmc_api.requests[0]
    assert request.url.params["sort"] == "relevance"
    assert request.url.params["resultType"] == "core"
    assert request.url.params["cursorMark"] == "*"


async def test_search_flattens_inline_markup_in_title_and_abstract(epmc_api):
    epmc_api.reply("/europepmc/webservices/rest/search", 200, json=ONE_RESULT)

    [entry] = await europe_pmc.search(epmc_api.client, "CRISPR", 10)

    assert entry["title"] == "The application of CRISPR gene-editing technology in the in vivo delivery."
    assert entry["abstract"] == "CRISPR enables in vivo gene editing."
    assert entry["pmid"] == "42428244"
    assert entry["pmcid"] == "13346171"
    assert entry["doi"] == "10.3389/fgeed.2026.1844919"
    assert entry["authors"] == ["Zhang X", "Shi H"]
    assert entry["year"] == 2026
    assert entry["cited_by_count"] == 3


async def test_a_record_missing_optional_fields_maps_without_them(epmc_api):
    epmc_api.reply(
        "/europepmc/webservices/rest/search", 200,
        json={"hitCount": 1, "resultList": {"result": [{"id": "1", "title": "Bare Record"}]}},
    )

    [entry] = await europe_pmc.search(epmc_api.client, "x", 1)

    assert entry == {
        "pmid": None, "pmcid": None, "title": "Bare Record", "authors": [], "year": None, "doi": None,
        "abstract": None, "cited_by_count": None,
    }  # fmt: skip


async def test_search_page_returns_entries_and_the_next_cursor_mark(epmc_api):
    epmc_api.reply("/europepmc/webservices/rest/search", 200, json=TWO_RESULTS_PAGE_1)

    entries, next_cursor = await europe_pmc.search_page(epmc_api.client, "x", 1, "*")

    assert [e["title"] for e in entries] == ["Paper One"]
    assert next_cursor == "AoIIQDaIlCg1NjQ3MDk5NA=="
    assert epmc_api.requests[0].url.params["cursorMark"] == "*"


async def test_search_page_stops_when_nextcursormark_disappears(epmc_api):
    epmc_api.reply("/europepmc/webservices/rest/search", 200, json=TWO_RESULTS_PAGE_2)

    entries, next_cursor = await europe_pmc.search_page(
        epmc_api.client, "x", 1, "AoIIQDaIlCg1NjQ3MDk5NA=="
    )

    assert [e["title"] for e in entries] == ["Paper Two"]
    assert next_cursor is None
    assert epmc_api.requests[0].url.params["cursorMark"] == "AoIIQDaIlCg1NjQ3MDk5NA=="


async def test_an_empty_query_404_raises_an_httpx_error(epmc_api):
    epmc_api.reply(
        "/europepmc/webservices/rest/search", 404,
        json={"errCode": 404, "errMsg": "No search criteria provided."},
    )

    with pytest.raises(httpx.HTTPError):
        await europe_pmc.search(epmc_api.client, "", 1)


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(epmc_api, status, body):
    epmc_api.reply("/europepmc/webservices/rest/search", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await europe_pmc.search(epmc_api.client, "x", 1)
