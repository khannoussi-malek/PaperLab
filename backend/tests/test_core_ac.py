import httpx
import pytest
from conftest import FakeProvider, recorded_discovery

from app.providers import core_ac

pytestmark = pytest.mark.anyio

# Without the trailing slash CORE answers 301.
SEARCH = "/v3/search/works/"


@pytest.fixture
async def core_api():
    fake = FakeProvider()
    fake.client = core_ac.new_client(None, transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_ands_the_title_words_in_the_title_field_on_the_trailing_slash_path(core_api):
    recording = recorded_discovery("core_search_attention")
    core_api.reply(SEARCH, 200, json=recording)

    works = await core_ac.search(core_api.client, "Attention Is All You Need", 5)

    assert works == recording["results"]
    [request] = core_api.requests
    assert request.url.path == SEARCH
    assert request.url.params["q"] == "title:(attention AND all AND you AND need)"
    assert request.url.params["limit"] == "5"
    assert "authorization" not in request.headers


async def test_operator_words_never_reach_the_query(core_api):
    # CORE answers 500 "Failed to parse query string" for and/or/not in any case.
    core_api.reply(SEARCH, 200, json={"results": []})

    await core_ac.search(core_api.client, "Pre-training AND Fine-tuning or not", 5)

    assert core_api.requests[0].url.params["q"] == "title:(pre AND training AND fine AND tuning)"


@pytest.mark.parametrize("title", ["", "?!", "Or not"])
async def test_a_title_with_no_search_words_sends_nothing(core_api, title):
    assert await core_ac.search(core_api.client, title, 5) == []
    assert core_api.requests == []


async def test_an_api_key_is_sent_as_a_bearer_header():
    fake = FakeProvider()
    fake.reply(SEARCH, 200, json={"results": []})
    async with core_ac.new_client("core-secret-key", transport=fake.transport) as client:
        await core_ac.search(client, "BERT", 5)

    assert fake.requests[0].headers["authorization"] == "Bearer core-secret-key"


async def test_a_refused_key_raises_a_status_error(core_api):
    core_api.reply(SEARCH, 401, json={"message": "The API key you provided is not valid."})

    with pytest.raises(httpx.HTTPStatusError) as caught:
        await core_ac.search(core_api.client, "BERT", 5)
    assert caught.value.response.status_code == 401


@pytest.mark.parametrize(
    ("status", "reply"),
    [
        (429, {"text": "Too many requests"}),
        (500, {"json": {"message": "Azure search failed"}}),
        (200, {"text": "<html>"}),
    ],
    ids=["rate limited", "server error", "malformed body"],
)
async def test_failures_raise_an_httpx_error(core_api, status, reply):
    core_api.reply(SEARCH, status, **reply)

    with pytest.raises(httpx.HTTPError):
        await core_ac.search(core_api.client, "BERT", 5)
