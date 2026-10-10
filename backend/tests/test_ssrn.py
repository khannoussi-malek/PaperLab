import httpx
import pytest
from conftest import FakeProvider

from app.providers import openalex, ssrn

pytestmark = pytest.mark.anyio

SSRN_WORK = {
    "id": "https://openalex.org/W1990513740",
    "doi": "https://doi.org/10.2139/ssrn.1496176",
    "title": "Diffusion of Innovations 1",
    "publication_year": 2026,
    "best_oa_location": None,
    "primary_location": {"source": {"display_name": "SSRN Electronic Journal"}},
    "locations": [],
    "authorships": [{"author": {"display_name": "Ada Fixture"}}],
    "cited_by_count": 9,
}
TWO_WORKS_PAGE_1 = {"meta": {"count": 2}, "results": [{"id": "https://openalex.org/W1", "title": "One"}]}
TWO_WORKS_PAGE_2 = {"meta": {"count": 2}, "results": [{"id": "https://openalex.org/W2", "title": "Two"}]}


@pytest.fixture
async def ssrn_api():
    fake = FakeProvider()
    fake.client = openalex.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_filters_to_ssrns_own_openalex_source_id(ssrn_api):
    ssrn_api.reply("/works", 200, json={"results": [SSRN_WORK]})

    [work] = await ssrn.search(ssrn_api.client, "diffusion innovation", 10)

    request = ssrn_api.requests[0]
    assert request.url.params["filter"] == "title.search:diffusion innovation,locations.source.id:S4210172589"
    assert work["title"] == "Diffusion of Innovations 1"


async def test_search_sends_the_same_field_selection_openalex_itself_uses(ssrn_api):
    ssrn_api.reply("/works", 200, json={"results": []})

    await ssrn.search(ssrn_api.client, "x", 1)

    assert ssrn_api.requests[0].url.params["select"] == openalex.WORK_FIELDS


async def test_a_work_with_no_pdf_anywhere_maps_without_one(ssrn_api):
    """Confirmed live: best_oa_location.pdf_url and primary_location.pdf_url are both null for every
    sampled SSRN record, even one flagged is_oa:true -- only a landing-page link is ever present, and
    this module's own search() never reads that field at all."""
    ssrn_api.reply("/works", 200, json={"results": [SSRN_WORK]})

    [work] = await ssrn.search(ssrn_api.client, "x", 1)

    assert work["best_oa_location"] is None
    assert (work.get("primary_location") or {}).get("pdf_url") is None


async def test_get_work_finds_a_record_by_openalex_id(ssrn_api):
    ssrn_api.reply("/works/W1990513740", 200, json=SSRN_WORK)

    work = await ssrn.get_work(ssrn_api.client, "W1990513740")

    assert work["title"] == "Diffusion of Innovations 1"


async def test_an_unknown_work_id_is_none(ssrn_api):
    ssrn_api.reply("/works/W999999999999", 404, text="not found")

    assert await ssrn.get_work(ssrn_api.client, "W999999999999") is None


async def test_search_page_keeps_the_ssrn_filter_on_every_page(ssrn_api):
    ssrn_api.reply("/works", 200, json=TWO_WORKS_PAGE_1)
    works_1, cursor_1 = await ssrn.search_page(ssrn_api.client, "x", 1, 0)

    ssrn_api.reply("/works", 200, json=TWO_WORKS_PAGE_2)
    works_2, cursor_2 = await ssrn.search_page(ssrn_api.client, "x", 1, cursor_1)

    filters = [ssrn_api.requests[0].url.params["filter"], ssrn_api.requests[1].url.params["filter"]]
    assert filters == [
        "title.search:x,locations.source.id:S4210172589", "title.search:x,locations.source.id:S4210172589",
    ]  # fmt: skip
    assert [w["title"] for w in works_1] == ["One"]
    assert cursor_1 == 1
    assert [w["title"] for w in works_2] == ["Two"]
    assert cursor_2 is None


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(ssrn_api, status, body):
    ssrn_api.reply("/works", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await ssrn.search(ssrn_api.client, "x", 1)
