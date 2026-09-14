import httpx
import pytest
from conftest import FakeOpenAlex, recorded

from app.providers import openalex

pytestmark = pytest.mark.anyio


async def test_every_request_carries_mailto_and_selects_only_the_fields_enrichment_reads(fake_openalex):
    fake_openalex.route("/works/doi:10.18653/v1/n19-1423", recorded("work_bert"))

    work = await openalex.get_work(fake_openalex.client, "doi:10.18653/v1/n19-1423")

    assert work["id"] == "https://openalex.org/W2963341956"
    [request] = fake_openalex.requests
    assert request.url.params["mailto"] == FakeOpenAlex.MAILTO
    assert request.url.params["select"] == openalex.WORK_FIELDS


async def test_a_work_openalex_does_not_have_is_none(fake_openalex):
    fake_openalex.route("/works/doi:10.9999/not-in-openalex", httpx.Response(404, text="<!doctype html>"))

    assert await openalex.get_work(fake_openalex.client, "doi:10.9999/not-in-openalex") is None


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(429, headers={"retry-after": "1"}, json={"error": "Rate limit exceeded"}),
        httpx.Response(503),
        httpx.ConnectError("OpenAlex unreachable"),
        httpx.ReadTimeout("OpenAlex timed out"),
    ],
    ids=["rate limited", "server error", "network error", "timeout"],
)
async def test_failures_raise_an_httpx_error_after_one_request(fake_openalex, failure):
    fake_openalex.route("/works/W1", failure)

    with pytest.raises(httpx.HTTPError):
        await openalex.get_work(fake_openalex.client, "W1")
    assert len(fake_openalex.requests) == 1


@pytest.mark.parametrize(
    ("route_path", "call"),
    [
        ("/works/W1", lambda client: openalex.get_work(client, "W1")),
        ("/works", lambda client: openalex.search_works(client, "BERT")),
        ("/authors", lambda client: openalex.get_authors(client, ["A1"])),
    ],
    ids=["get_work", "search_works", "get_authors"],
)
async def test_a_malformed_200_body_raises_an_httpx_error(fake_openalex, route_path, call):
    # A proxy or an OpenAlex outage can answer 200 with an HTML page instead of JSON.
    fake_openalex.route(route_path, httpx.Response(200, text="<!doctype html>"))

    with pytest.raises(httpx.HTTPError):
        await call(fake_openalex.client)


async def test_title_search_strips_the_characters_openalex_rejects_in_a_filter(fake_openalex):
    fake_openalex.route("/works", recorded("search_no_match"))

    assert await openalex.search_works(fake_openalex.client, "Dementia prevention, intervention|care") == []

    [request] = fake_openalex.requests
    assert request.url.params["filter"] == "title.search:Dementia prevention  intervention care"
    assert request.url.params["per-page"] == "5"


async def test_authors_are_fetched_fifty_ids_per_request(fake_openalex):
    fake_openalex.route("/authors", recorded("authors_bert"), {"results": []})
    ids = [f"A{n}" for n in range(51)]

    records = await openalex.get_authors(fake_openalex.client, ids)

    assert len(records) == 4
    first, second = fake_openalex.requests
    assert first.url.params["filter"] == "openalex_id:" + "|".join(ids[:50])
    assert first.url.params["per-page"] == "50"
    assert second.url.params["filter"] == "openalex_id:A50"
