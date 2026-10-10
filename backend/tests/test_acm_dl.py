import httpx
import pytest
from conftest import FakeProvider

from app.providers import acm_dl, crossref

pytestmark = pytest.mark.anyio

ACM_ITEM = {
    "DOI": "10.1145/3577923.3583658",
    "type": "proceedings-article",
    "title": ["AutoSpill: Credential Leakage from Mobile Password Managers"],
    "author": [{"given": "Andrea", "family": "Possemato"}],
    "issued": {"date-parts": [[2026]]},
    "container-title": ["Proceedings of the ACM"],
    "is-referenced-by-count": 12,
}
TWO_ITEMS_PAGE_1 = {
    "message": {"items": [{"DOI": "10.1145/1", "title": ["One"]}, {"DOI": "10.1145/2", "title": ["Two"]}]}
}
SHORT_PAGE_2 = {"message": {"items": [{"DOI": "10.1145/3", "title": ["Three"]}]}}


@pytest.fixture
async def acm_api():
    fake = FakeProvider()
    fake.client = crossref.new_client(transport=fake.transport)
    yield fake
    await fake.client.aclose()


async def test_search_filters_to_the_acm_doi_prefix(acm_api):
    acm_api.reply("/works", 200, json={"message": {"items": [ACM_ITEM]}})

    [item] = await acm_dl.search(acm_api.client, "AutoSpill", 10)

    request = acm_api.requests[0]
    assert request.url.params["filter"] == "prefix:10.1145"
    assert request.url.params["query.bibliographic"] == "AutoSpill"
    assert item["DOI"] == "10.1145/3577923.3583658"


async def test_search_sends_the_same_field_selection_crossref_itself_uses(acm_api):
    acm_api.reply("/works", 200, json={"message": {"items": []}})

    await acm_dl.search(acm_api.client, "x", 1)

    assert acm_api.requests[0].url.params["select"] == crossref.FIELDS


async def test_search_with_no_abstract_field_at_all_does_not_crash(acm_api):
    """Most ACM works carry no abstract (confirmed live, ~16% do) -- Crossref's own response simply omits
    the key entirely rather than sending null."""
    acm_api.reply("/works", 200, json={"message": {"items": [ACM_ITEM]}})

    [item] = await acm_dl.search(acm_api.client, "x", 1)

    assert "abstract" not in item


async def test_get_work_finds_a_record_by_doi(acm_api):
    # The slash in a DOI stays literal in the request path (quote(doi, safe='/:')), matching
    # crossref.py's own get_work and its own test (test_crossref.py's test_get_work_by_doi).
    acm_api.reply("/works/10.1145/3577923.3583658", 200, json={"message": ACM_ITEM})

    item = await acm_dl.get_work(acm_api.client, "10.1145/3577923.3583658")

    assert item["DOI"] == "10.1145/3577923.3583658"


async def test_an_unknown_doi_is_none(acm_api):
    acm_api.reply("/works/10.1145/nonexistent", 404, text="Resource not found.")

    assert await acm_dl.get_work(acm_api.client, "10.1145/nonexistent") is None


async def test_search_page_keeps_the_acm_filter_on_every_page(acm_api):
    """page_size=2: page 1 comes back full (2 items, signals "more"), page 2 comes back short (1 item,
    signals "no more") -- the same full/short convention crossref.py's own next_cursor rule uses
    (len(items) == page_size), not a links.next-style flag like Zenodo's."""
    acm_api.reply("/works", 200, json=TWO_ITEMS_PAGE_1)
    items_1, cursor_1 = await acm_dl.search_page(acm_api.client, "x", 2, 0)

    acm_api.reply("/works", 200, json=SHORT_PAGE_2)
    items_2, cursor_2 = await acm_dl.search_page(acm_api.client, "x", 2, cursor_1)

    assert [acm_api.requests[0].url.params["filter"], acm_api.requests[1].url.params["filter"]] == [
        "prefix:10.1145", "prefix:10.1145",
    ]  # fmt: skip
    assert [i["DOI"] for i in items_1] == ["10.1145/1", "10.1145/2"]
    assert cursor_1 == 2
    assert [i["DOI"] for i in items_2] == ["10.1145/3"]
    assert cursor_2 is None


@pytest.mark.parametrize(
    ("status", "body"), [(503, "busy"), (429, "Rate exceeded.")], ids=["server error", "rate limited"]
)
async def test_failures_raise_an_httpx_error(acm_api, status, body):
    acm_api.reply("/works", status, text=body)

    with pytest.raises(httpx.HTTPError):
        await acm_dl.search(acm_api.client, "x", 1)
