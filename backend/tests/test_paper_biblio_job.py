import dataclasses
from contextlib import asynccontextmanager

import httpx
import pytest

from app.core import paper_sources, papers, queue
from app.models import Paper
from app.workers import paper_biblio as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]
DOI = "10.1037/0022-3514.45.2.357"
WORK = {"DOI": DOI, "volume": "45", "issue": "2", "page": "357-376", "type": "journal-article"}


@pytest.fixture(autouse=True)
def wiring(session, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)


def crossref_says(work):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if "openalex" in request.url.host:
            return httpx.Response(404)
        return httpx.Response(200, json={"message": work}) if work else httpx.Response(404)

    return httpx.MockTransport(handler), seen


async def saved(session, **kw):
    prefill = {"doi": DOI, "title": "The social psychology of creativity", **kw}
    return await papers.create_metadata_paper(session, prefill, "crossref", looked_for_pdf=True)


async def test_a_paper_saved_without_its_pdf_gets_volume_issue_and_pages_from_crossref(session):
    paper = await saved(session)
    transport, seen = crossref_says(WORK)
    await worker.fill_paper_biblio({"transport": transport}, str(paper.id))
    await session.refresh(paper)
    assert (paper.volume, paper.issue, paper.pages) == ("45", "2", "357-376")
    assert any(DOI in path for path in seen)


async def test_values_already_held_are_kept(session):
    paper = await saved(session, volume="99")
    transport, _ = crossref_says(WORK)
    await worker.fill_paper_biblio({"transport": transport}, str(paper.id))
    await session.refresh(paper)
    assert (paper.volume, paper.pages) == ("99", "357-376")


async def test_crossref_off_in_settings_asks_nobody(session, monkeypatch):
    paper = await saved(session)
    transport, seen = crossref_says(WORK)
    real = paper_sources.get

    async def crossref_off(s):
        got = await real(s)
        return dataclasses.replace(got, enabled={**got.enabled, "crossref": False, "openalex": False})

    monkeypatch.setattr(paper_sources, "get", crossref_off)
    await worker.fill_paper_biblio({"transport": transport}, str(paper.id))
    await session.refresh(paper)
    assert seen == [] and paper.volume is None


async def test_a_gone_paper_or_a_failing_source_never_raises(session):
    import uuid

    await worker.fill_paper_biblio({}, str(uuid.uuid4()))
    paper = await saved(session)
    broken = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("dns")))
    await worker.fill_paper_biblio({"transport": broken}, str(paper.id))
    await session.refresh(paper)
    assert paper.volume is None


async def test_queue_biblio_fill_asks_only_for_a_paper_with_a_doi(session, monkeypatch):
    from conftest import FakeArq

    pool = FakeArq()
    monkeypatch.setattr(queue, "_pool", pool)
    with_doi = await saved(session)
    without = await papers.create_metadata_paper(session, {"title": "No DOI here"}, "crossref", looked_for_pdf=True)
    await papers.queue_biblio_fill(with_doi)
    await papers.queue_biblio_fill(without)
    assert pool.jobs == [("fill_paper_biblio", str(with_doi.id))]
    assert isinstance(with_doi, Paper)
