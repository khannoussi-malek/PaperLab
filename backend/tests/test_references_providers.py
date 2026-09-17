"""M7.5 references panel: the provider calls core/references.py will use (spec §4). Fixtures recorded live by
tests/fixtures/references/record.py.
"""

import copy
import json
from pathlib import Path

import httpx
import pytest
from conftest import FakeProvider

from app.providers import openalex, semantic_scholar

pytestmark = pytest.mark.anyio

REFERENCES_FIXTURES = Path(__file__).parent / "fixtures" / "references"

BERT_DOI_KEY = "DOI:10.18653/v1/n19-1423"
BERT_REFERENCES_PATH = "/graph/v1/paper/DOI:10.18653/v1/n19-1423/references"
BERT_CITATIONS_PATH = "/graph/v1/paper/DOI:10.18653/v1/n19-1423/citations"
BERT_OPENALEX_ID = "W2963341956"


def recorded_references(name: str) -> dict:
    """A body recorded by tests/fixtures/references/record.py."""
    return json.loads((REFERENCES_FIXTURES / f"{name}.json").read_text())


class PagedS2:
    """A local fake for Semantic Scholar's references/citations paging. FakeProvider (conftest) keeps one reply
    per path, but paging sends several requests to the very same path, differing only by `offset`; this fake
    routes by (path, offset) instead. An unrouted request fails loudly, like FakeProvider's."""

    def __init__(self):
        self.pages: dict[tuple[str, str], dict] = {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def page(self, path: str, offset: int, body: dict) -> None:
        self.pages[(path, str(offset))] = body

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.url.path, request.url.params.get("offset", "0"))
        if key not in self.pages:
            raise AssertionError(f"unrouted paged S2 request: {request.url}")
        return httpx.Response(200, json=self.pages[key])


@pytest.fixture
async def s2():
    fake = FakeProvider()
    fake.client = semantic_scholar.new_client("", transport=fake.transport)
    yield fake
    await fake.client.aclose()


@pytest.fixture
async def paged_s2():
    fake = PagedS2()
    client = semantic_scholar.new_client("", transport=fake.transport)
    yield fake, client
    await client.aclose()


# --- semantic_scholar.references / .citations -------------------------------------------------------------------


async def test_references_pages_until_next_is_absent(paged_s2):
    fake, client = paged_s2
    page1, page2 = recorded_references("s2_references_bert_page1"), recorded_references("s2_references_bert_page2")
    fake.page(BERT_REFERENCES_PATH, 0, page1)
    fake.page(BERT_REFERENCES_PATH, 40, page2)

    records = await semantic_scholar.references(client, BERT_DOI_KEY, cap=1000)

    assert len(records) == 40 + 23
    assert [r["title"] for r in records[:2]] == [item["citedPaper"]["title"] for item in page1["data"][:2]]
    [first, second] = fake.requests
    assert first.url.params["offset"] == "0"
    assert first.url.params["limit"] == str(semantic_scholar.PAGE)
    assert first.url.params["fields"] == semantic_scholar.PAPER_FIELDS
    assert second.url.params["offset"] == "40"


async def test_references_stops_once_the_cap_is_reached(paged_s2):
    fake, client = paged_s2
    page1 = recorded_references("s2_references_bert_page1")
    fake.page(BERT_REFERENCES_PATH, 0, page1)
    fake.page(BERT_REFERENCES_PATH, 40, recorded_references("s2_references_bert_page2"))  # must stay unrequested

    records = await semantic_scholar.references(client, BERT_DOI_KEY, cap=5)

    assert len(records) == 5
    assert [r["title"] for r in records] == [item["citedPaper"]["title"] for item in page1["data"][:5]]
    assert len(fake.requests) == 1  # the cap was already met inside page 1: page 2 is never asked for


async def test_references_returns_the_inner_cited_paper_dicts_in_order(paged_s2):
    fake, client = paged_s2
    page1, page2 = recorded_references("s2_references_bert_page1"), recorded_references("s2_references_bert_page2")
    fake.page(BERT_REFERENCES_PATH, 0, page1)
    fake.page(BERT_REFERENCES_PATH, 40, page2)

    records = await semantic_scholar.references(client, BERT_DOI_KEY, cap=1000)

    expected = [item["citedPaper"] for item in page1["data"]] + [item["citedPaper"] for item in page2["data"]]
    assert records == expected


async def test_references_skips_items_missing_their_inner_record(paged_s2):
    fake, client = paged_s2
    page1 = copy.deepcopy(recorded_references("s2_references_bert_page1"))
    page1["data"].insert(0, {"citedPaper": None})  # S2 sometimes lists a paper it can't describe
    page1["data"].insert(0, {})  # and sometimes leaves the key out entirely
    fake.page(BERT_REFERENCES_PATH, 0, page1)
    fake.page(BERT_REFERENCES_PATH, 40, recorded_references("s2_references_bert_page2"))

    records = await semantic_scholar.references(client, BERT_DOI_KEY, cap=1000)

    assert len(records) == 40 + 23  # the two malformed items added nothing, and nothing crashed
    assert all(r for r in records)


async def test_references_to_an_unknown_paper_is_none(s2):
    unknown = recorded_references("s2_references_unknown")
    s2.reply("/graph/v1/paper/DOI:10.9999/not-in-s2/references", unknown["status"], json=unknown["body"])

    assert await semantic_scholar.references(s2.client, "DOI:10.9999/not-in-s2", cap=100) is None


async def test_citations_asks_the_citations_endpoint_for_citing_paper_dicts(paged_s2):
    fake, client = paged_s2
    page1 = recorded_references("s2_citations_bert_page1")
    fake.page(BERT_CITATIONS_PATH, 0, page1)
    fake.page(BERT_CITATIONS_PATH, 5, {"offset": 5, "data": []})  # tail: no "next"

    records = await semantic_scholar.citations(client, BERT_DOI_KEY, cap=1000)

    assert records == [item["citingPaper"] for item in page1["data"]]
    [first, second] = fake.requests
    assert first.url.path == BERT_CITATIONS_PATH
    assert second.url.params["offset"] == "5"


async def test_citations_stops_once_the_cap_is_reached(paged_s2):
    fake, client = paged_s2
    page1 = recorded_references("s2_citations_bert_page1")
    fake.page(BERT_CITATIONS_PATH, 0, page1)
    fake.page(BERT_CITATIONS_PATH, 5, {"offset": 5, "data": []})  # must stay unrequested

    records = await semantic_scholar.citations(client, BERT_DOI_KEY, cap=3)

    assert len(records) == 3
    assert len(fake.requests) == 1


async def test_citations_to_an_unknown_paper_is_none(s2):
    unknown = recorded_references("s2_references_unknown")  # the 404 body is the same shape for any endpoint
    s2.reply("/graph/v1/paper/DOI:10.9999/not-in-s2/citations", unknown["status"], json=unknown["body"])

    assert await semantic_scholar.citations(s2.client, "DOI:10.9999/not-in-s2", cap=100) is None


S2_CALLS = [
    (lambda client: semantic_scholar.references(client, BERT_DOI_KEY, cap=10), BERT_REFERENCES_PATH),
    (lambda client: semantic_scholar.citations(client, BERT_DOI_KEY, cap=10), BERT_CITATIONS_PATH),
]


@pytest.mark.parametrize(("call", "path"), S2_CALLS, ids=["references", "citations"])
@pytest.mark.parametrize("status", [429, 503], ids=["rate limited", "server error"])
async def test_an_error_status_raises_an_httpx_error(s2, call, path, status):
    s2.reply(path, status, json={"message": "busy"})
    with pytest.raises(httpx.HTTPStatusError):
        await call(s2.client)


@pytest.mark.parametrize(("call", "path"), S2_CALLS, ids=["references", "citations"])
async def test_a_refused_connection_raises_an_httpx_error(s2, call, path):
    s2.refuse(path)  # FakeProvider's stand-in for a network failure (connection refused)
    with pytest.raises(httpx.HTTPError):
        await call(s2.client)


async def test_a_malformed_body_raises_an_http_error(s2):
    s2.reply(BERT_REFERENCES_PATH, 200, text="<html>proxy login</html>")

    with pytest.raises(httpx.HTTPError):
        await semantic_scholar.references(s2.client, BERT_DOI_KEY, cap=10)


# --- openalex.referenced_works / .works_by_ids / .citing_works ----------------------------------------------------


async def test_referenced_works_returns_short_ids(fake_openalex):
    body = recorded_references("openalex_referenced_works_bert")
    fake_openalex.route(f"/works/{BERT_OPENALEX_ID}", body)

    ids = await openalex.referenced_works(fake_openalex.client, BERT_OPENALEX_ID)

    assert len(ids) == 52
    assert ids == [url.rsplit("/", 1)[-1] for url in body["referenced_works"]]
    assert all(i.startswith("W") for i in ids)
    [request] = fake_openalex.requests
    assert request.url.params["select"] == "referenced_works"


async def test_referenced_works_for_an_unknown_work_is_empty(fake_openalex):
    fake_openalex.route("/works/W0", httpx.Response(404, text="<!doctype html>"))

    assert await openalex.referenced_works(fake_openalex.client, "W0") == []


async def test_works_by_ids_batches_fifty_ids_per_request(fake_openalex):
    ids = [f"W{n}" for n in range(51)]
    fake_openalex.route(f"/works?openalex_id:{'|'.join(ids[:50])}", {"results": [{"id": "https://openalex.org/W0"}]})
    fake_openalex.route("/works?openalex_id:W50", {"results": [{"id": "https://openalex.org/W50"}]})

    records = await openalex.works_by_ids(fake_openalex.client, ids)

    assert [r["id"] for r in records] == ["https://openalex.org/W0", "https://openalex.org/W50"]
    first, second = fake_openalex.requests
    assert first.url.params["filter"] == "openalex_id:" + "|".join(ids[:50])
    assert first.url.params["per-page"] == "50"
    assert first.url.params["select"] == openalex.WORK_FIELDS
    assert second.url.params["filter"] == "openalex_id:W50"


async def test_works_by_ids_returns_the_recorded_batch_in_openalexs_order(fake_openalex):
    body = recorded_references("openalex_works_by_ids_batch")
    two_ids = [w["id"].rsplit("/", 1)[-1] for w in body["results"]]
    fake_openalex.route(f"/works?openalex_id:{'|'.join(two_ids)}", body)

    records = await openalex.works_by_ids(fake_openalex.client, two_ids)

    assert records == body["results"]


async def test_citing_works_asks_cites_filter_sorted_newest_first(fake_openalex):
    body = recorded_references("openalex_citing_works_page")
    fake_openalex.route(f"/works?cites:{BERT_OPENALEX_ID}", body)

    records = await openalex.citing_works(fake_openalex.client, BERT_OPENALEX_ID, limit=5)

    assert records == body["results"]
    [request] = fake_openalex.requests
    assert request.url.params["filter"] == f"cites:{BERT_OPENALEX_ID}"
    assert request.url.params["sort"] == "publication_date:desc"
    assert request.url.params["per-page"] == "5"
    assert request.url.params["select"] == openalex.WORK_FIELDS


async def test_citing_works_caps_per_page_at_two_hundred(fake_openalex):
    body = recorded_references("openalex_citing_works_page")
    fake_openalex.route(f"/works?cites:{BERT_OPENALEX_ID}", body, body)

    await openalex.citing_works(fake_openalex.client, BERT_OPENALEX_ID, limit=5)
    await openalex.citing_works(fake_openalex.client, BERT_OPENALEX_ID, limit=500)

    assert [r.url.params["per-page"] for r in fake_openalex.requests] == ["5", "200"]


@pytest.mark.parametrize(
    ("route_path", "call"),
    [
        (f"/works/{BERT_OPENALEX_ID}", lambda client: openalex.referenced_works(client, BERT_OPENALEX_ID)),
        (f"/works?openalex_id:{BERT_OPENALEX_ID}", lambda client: openalex.works_by_ids(client, [BERT_OPENALEX_ID])),
        (f"/works?cites:{BERT_OPENALEX_ID}", lambda client: openalex.citing_works(client, BERT_OPENALEX_ID, 5)),
    ],
    ids=["referenced_works", "works_by_ids", "citing_works"],
)
async def test_openalex_failures_raise_an_httpx_error(fake_openalex, route_path, call):
    fake_openalex.route(route_path, httpx.ConnectError("OpenAlex unreachable"))
    with pytest.raises(httpx.HTTPError):
        await call(fake_openalex.client)


@pytest.mark.parametrize(
    ("route_path", "call"),
    [
        (f"/works/{BERT_OPENALEX_ID}", lambda client: openalex.referenced_works(client, BERT_OPENALEX_ID)),
        (f"/works?openalex_id:{BERT_OPENALEX_ID}", lambda client: openalex.works_by_ids(client, [BERT_OPENALEX_ID])),
        (f"/works?cites:{BERT_OPENALEX_ID}", lambda client: openalex.citing_works(client, BERT_OPENALEX_ID, 5)),
    ],
    ids=["referenced_works", "works_by_ids", "citing_works"],
)
async def test_openalex_malformed_200_body_raises_an_httpx_error(fake_openalex, route_path, call):
    fake_openalex.route(route_path, httpx.Response(200, text="<!doctype html>"))
    with pytest.raises(httpx.HTTPError):
        await call(fake_openalex.client)
