import httpx
import pytest
from conftest import FakeProvider, recorded_discovery

from app.providers import crossref

pytestmark = pytest.mark.anyio

BERT_DOI = "10.18653/v1/n19-1423"


@pytest.fixture
async def crossref_api():
    fake = FakeProvider()
    fake.client = crossref.new_client(None, transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_asks_for_a_bibliographic_match_with_only_the_fields_the_mapper_reads(crossref_api):
    recording = recorded_discovery("crossref_search_attention")
    crossref_api.reply("/works", 200, json=recording)

    items = await crossref.search(crossref_api.client, "attention is all you need", 5)

    assert items == recording["message"]["items"]
    [request] = crossref_api.requests
    assert request.url.params["query.bibliographic"] == "attention is all you need"
    assert request.url.params["rows"] == "5"
    assert request.url.params["select"] == crossref.FIELDS
    assert "mailto" not in request.url.params


async def test_the_contact_email_is_sent_as_mailto_when_set():
    fake = FakeProvider()
    fake.reply("/works", 200, json={"message": {"items": []}})
    async with crossref.new_client("reader@example.org", transport=fake.transport) as client:
        await crossref.search(client, "BERT", 5)

    assert fake.requests[0].url.params["mailto"] == "reader@example.org"


async def test_get_work_by_doi(crossref_api):
    crossref_api.reply(f"/works/{BERT_DOI}", 200, json=recorded_discovery("crossref_work_bert"))

    work = await crossref.get_work(crossref_api.client, BERT_DOI)

    assert work["DOI"].lower() == BERT_DOI
    assert work["type"] == "proceedings-article"


async def test_a_doi_crossref_does_not_have_is_none(crossref_api):
    # Crossref's 404 body is plain text, not JSON.
    crossref_api.reply("/works/10.9999/not-in-crossref", 404, text="Resource not found.")

    assert await crossref.get_work(crossref_api.client, "10.9999/not-in-crossref") is None


async def test_a_doi_containing_a_question_mark_is_percent_encoded_not_truncated_into_a_query(crossref_api):
    crossref_api.reply("/works/10.1000/abc?xyz", 200, json=recorded_discovery("crossref_work_bert"))

    assert await crossref.get_work(crossref_api.client, "10.1000/abc?xyz")
    assert crossref_api.requests[0].url.path == "/works/10.1000/abc?xyz"


@pytest.mark.parametrize(
    ("status", "reply"),
    [
        (429, {"text": "Rate limit exceeded"}),
        (503, {"text": "busy"}),
        (200, {"text": "<!doctype html>"}),
    ],
    ids=["rate limited", "server error", "malformed body"],
)
async def test_failures_raise_an_httpx_error(crossref_api, status, reply):
    crossref_api.reply("/works", status, **reply)
    crossref_api.reply(f"/works/{BERT_DOI}", status, **reply)

    with pytest.raises(httpx.HTTPError):
        await crossref.search(crossref_api.client, "BERT", 5)
    with pytest.raises(httpx.HTTPError):
        await crossref.get_work(crossref_api.client, BERT_DOI)
