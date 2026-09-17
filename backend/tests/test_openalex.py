import httpx
import pytest
from conftest import FakeOpenAlex, FakeProvider, recorded

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


async def test_a_merged_works_301_redirect_is_followed(fake_openalex):
    # OpenAlex answers a merged-away work id with a 301 to the record it was merged into. A relative Location
    # replaces the whole query string (RFC 3986), so it must repeat mailto for every request to still carry one.
    location = f"/works/W123?mailto={FakeOpenAlex.MAILTO}"
    fake_openalex.route("/works/W999", httpx.Response(301, headers={"location": location}))
    fake_openalex.route("/works/W123", recorded("work_bert"))

    work = await openalex.get_work(fake_openalex.client, "W999")

    assert work["id"] == "https://openalex.org/W2963341956"
    assert [r.url.path for r in fake_openalex.requests] == ["/works/W999", "/works/W123"]


async def test_a_doi_containing_a_question_mark_is_percent_encoded_not_truncated_into_a_query(fake_openalex):
    # "?" inside a DOI path segment must not be read as the start of the query string.
    fake_openalex.route("/works/doi:10.1000/abc?xyz", recorded("work_bert"))

    work = await openalex.get_work(fake_openalex.client, "doi:10.1000/abc?xyz")

    assert work["id"] == "https://openalex.org/W2963341956"
    [request] = fake_openalex.requests
    assert request.url.path == "/works/doi:10.1000/abc?xyz"
    assert request.url.params["select"] == openalex.WORK_FIELDS  # the real query string still parses


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


async def test_search_works_asks_for_as_many_results_as_the_caller_wants(fake_openalex):
    fake_openalex.route("/works", recorded("search_bert"))

    await openalex.search_works(fake_openalex.client, "BERT", per_page=10)
    await openalex.search_works(fake_openalex.client, "BERT")

    assert [r.url.params["per-page"] for r in fake_openalex.requests] == ["10", str(openalex.SEARCH_RESULTS)]


def test_works_are_fetched_with_their_locations_for_discovery():
    assert "locations" in openalex.WORK_FIELDS.split(",")


async def test_without_an_email_no_mailto_is_sent():
    fake = FakeProvider()
    fake.reply("/works/W1", 200, json=recorded("work_bert"))
    async with openalex.new_client(None, transport=fake.transport) as client:
        await openalex.get_work(client, "W1")

    assert "mailto" not in fake.requests[0].url.params
    assert "authorization" not in fake.requests[0].headers


async def test_an_api_key_travels_only_in_the_bearer_header_never_in_a_url():
    # httpx puts the URL in its error messages, and enrichment logs those with logger.exception.
    key = "openalex-secret-key"
    fake = FakeProvider()
    fake.reply("/works", 200, json=recorded("search_bert"))
    fake.reply("/works/W1", 401, json={"error": "Invalid or missing API key"})
    async with openalex.new_client(FakeOpenAlex.MAILTO, transport=fake.transport, api_key=key) as client:
        await openalex.search_works(client, "BERT")
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await openalex.get_work(client, "W1")

    assert [r.headers["authorization"] for r in fake.requests] == [f"Bearer {key}"] * 2
    assert not any(key in str(r.url) for r in fake.requests)
    assert key not in str(caught.value)
