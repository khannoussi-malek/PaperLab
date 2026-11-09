import uuid
from types import SimpleNamespace

import pytest
from conftest import FakeProvider

from app.core import manuscripts, queue
from app.core.manuscript_checks import doi_service
from app.providers import crossref

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


@pytest.fixture(autouse=True)
def wiring(arq, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)


async def made_with_bib(client, session):
    mid = (await client.post("/api/manuscripts", json={"title": "D", "template": "article"})).json()["id"]
    await manuscripts.upsert_text(session, uuid.UUID(mid), "refs.bib",
                                  "@article{a, doi={10.1000/abc}}\n@article{d, doi={10.1000/gone}}\n")
    return mid


def wire_fake(monkeypatch, enabled=True):
    fake = FakeProvider()
    fake.reply("/works/10.1000/abc", 200, json={"message": {"DOI": "10.1000/abc"}})
    fake.reply("/works/10.1000/gone", 404)
    monkeypatch.setattr(doi_service, "new_client", lambda email: crossref.new_client(email=email, transport=fake.transport))

    async def get(_session):
        return SimpleNamespace(enabled={"crossref": enabled}, contact_email="me@x.org")

    monkeypatch.setattr(doi_service.paper_sources, "get", get)
    return fake


async def test_dois_route_returns_counts_and_findings(client, session, monkeypatch):
    mid = await made_with_bib(client, session)
    fake = wire_fake(monkeypatch)
    r = await client.post(f"/api/manuscripts/{mid}/checks/dois")
    assert r.status_code == 200
    body = r.json()
    assert (body["checked"], body["not_checked"]) == (2, 0)
    assert all(not q.url.params for q in fake.requests)
    assert body["counts"] == {"error": 1, "warning": 0, "info": 0}
    assert set(body["findings"][0]) == {"check", "severity", "file", "line", "message", "fix_hint"}


async def test_dois_route_errors(client, session, monkeypatch):
    assert (await client.post(f"/api/manuscripts/{uuid.uuid4()}/checks/dois")).status_code == 404
    mid = await made_with_bib(client, session)
    wire_fake(monkeypatch, enabled=False)
    r = await client.post(f"/api/manuscripts/{mid}/checks/dois")
    assert r.status_code == 422
