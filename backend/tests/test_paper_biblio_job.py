import dataclasses
from contextlib import asynccontextmanager

import httpx
import pytest

from app.core import paper_sources, papers, queue
from app.models import Paper
from app.providers import crossref
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


def crossref_client(transport):
    return crossref.new_client(transport=transport)


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


async def test_a_paper_saved_without_its_pdf_learns_its_type_and_peer_review_status(session):
    paper = await saved(session, venue="Proceedings of the 36th International Conference on Software Engineering")
    assert paper.peer_reviewed == "unknown"
    transport, _ = crossref_says({**WORK, "type": "proceedings-article"})
    await worker.fill_paper_biblio({"transport": transport}, str(paper.id))
    await session.refresh(paper)
    assert (paper.source_type, paper.peer_reviewed) == ("proceedings", "true")


async def test_a_type_the_owner_set_by_hand_is_kept(session):
    paper = await saved(session)
    paper.source_type, paper.manual_fields = "book", ["source_type"]
    await session.flush()
    transport, _ = crossref_says({**WORK, "type": "journal-article"})
    await worker.fill_paper_biblio({"transport": transport}, str(paper.id))
    await session.refresh(paper)
    assert paper.source_type == "book"


async def test_the_backfill_fills_source_types_only_when_asked_and_reports_them(session, tmp_path):
    from app.scripts import backfill_biblio

    paper = await saved(session)
    transport, _ = crossref_says({**WORK, "type": "journal-article"})
    report = tmp_path / "types.csv"
    async with crossref_client(transport) as http:
        summary = await backfill_biblio.run_source_types(session, http, delay=0, only=[paper.id], report=report)
    await session.refresh(paper)
    assert summary == {"checked": 1, "updated": 1}
    assert (paper.source_type, paper.peer_reviewed) == ("journal_article", "true")
    assert "source_type,,journal_article" in report.read_text()
