"""The check_dois MCP tool: the same run as the API's Check DOIs online, through an in-process client, with Crossref on
a mock transport (never the real network)."""

import uuid

import pytest
from conftest import FakeProvider
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call
from test_manuscript_check_references_doi import BIB, wire
from test_manuscript_papers import setup

from app.core import manuscripts

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


@pytest.fixture
def crossref_fake():
    return FakeProvider()


async def manuscript_with(session, bib=BIB):
    _, _, m = await setup(session, "Deep learning", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "refs.bib", bib)
    return m


async def test_a_resolving_and_a_non_resolving_doi(session, monkeypatch, crossref_fake):
    m = await manuscript_with(session)
    crossref_fake.reply("/works/10.1000/abc", 200, json={"message": {"DOI": "10.1000/abc"}})
    crossref_fake.reply("/works/10.1000/gone", 404)
    wire(monkeypatch, crossref_fake)

    response = await call("check_dois", manuscript_id=str(m.id))

    assert not response.is_error, response.content
    out = response.structured_content
    assert (out["checked"], out["not_checked"]) == (2, 0)
    [finding] = out["findings"]
    assert finding["severity"] == "error"
    assert finding["message"] == "DOI 10.1000/gone (entry d) was not found at Crossref."


async def test_only_the_dois_are_sent_and_no_email(session, monkeypatch, crossref_fake):
    m = await manuscript_with(session, "@article{a, doi={10.1000/abc}}\n")
    crossref_fake.reply("/works/10.1000/abc", 200, json={"message": {"DOI": "10.1000/abc"}})
    wire(monkeypatch, crossref_fake, email="me@x.org")

    await call("check_dois", manuscript_id=str(m.id))

    [request] = crossref_fake.requests
    assert request.url.path == "/works/10.1000/abc" and not request.url.params
    assert request.content == b"" and "me@x.org" not in str(request.url)


async def test_crossref_turned_off_passes_its_error_through_and_sends_nothing(session, monkeypatch, crossref_fake):
    m = await manuscript_with(session)
    wire(monkeypatch, crossref_fake, enabled=False)

    response = await call("check_dois", manuscript_id=str(m.id))

    assert response.is_error
    assert response.structured_content["error"] == "crossref_disabled"
    assert crossref_fake.requests == []
