"""R20/R21: the weekly free-copy re-check, its switch, paper events and the Found PDFs routes."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.api.deps import get_discovery
from app.core import discovery, paper_events, papers, pdf_recheck, queue
from app.models import Paper, PaperEvent, PaperSources
from app.workers import pdf_recheck as worker

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.7\n%a found paper\n"
HOST = "https://pdf.example"
NOW = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fake_queue(arq, monkeypatch):
    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(pdf_recheck, "sleep", _no_sleep)


async def _no_sleep(_seconds):
    return None


async def held(session, title="Sleep and memory", **fields) -> Paper:
    prefill = {"title": title, "abstract": "Sleep helps memory.", "manual_fields": ["title"], **fields}
    return await papers.create_metadata_paper(session, prefill, "crossref")


async def test_a_found_copy_upgrades_the_paper_and_leaves_an_event(session, arq, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    paper = await held(session, oa_url=f"{HOST}/copy.pdf")

    outcome = await pdf_recheck.recheck(session, discovery_fakes.providers, paper.id, NOW)

    await session.refresh(paper)
    assert outcome == "found"
    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert (paper.pdf_checked_at, paper.pdf_check_result) == (NOW, "found")
    assert arq.jobs == [("ingest_paper", str(paper.id))]
    [event] = await paper_events.history(session, paper.id)
    assert (event.kind, event.detail) == ("pdf_found", {"url": f"{HOST}/copy.pdf", "how": "imported"})


async def test_no_copy_records_none_and_a_failure_records_error_and_the_run_goes_on(
    session, arq, discovery_fakes, pdf_dir, monkeypatch
):
    discovery_fakes.pdf_host.reply("/gone.pdf", 404)
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    lost = await held(session, "Lost", oa_url=f"{HOST}/gone.pdf")
    broken = await held(session, "Broken")
    found = await held(session, "Found", oa_url=f"{HOST}/copy.pdf")
    real, broken_id, found_id = discovery.find_pdf, broken.id, found.id  # a rollback expires the objects

    async def flaky(session_, providers, candidate):
        if candidate.paper_id == broken_id:
            raise RuntimeError("boom")
        return await real(session_, providers, candidate)

    monkeypatch.setattr(discovery, "find_pdf", flaky)
    # the run order is the checked-at order: never-checked first, then by created_at
    counts = await pdf_recheck.run(session, discovery_fakes.providers, NOW)

    for paper in (lost, broken, found):
        await session.refresh(paper)
    assert counts == {"found": 1, "none": 1, "error": 1, "skipped": 0}
    assert [p.pdf_check_result for p in (lost, broken, found)] == ["none", "error", "found"]
    assert all(p.pdf_checked_at == NOW for p in (lost, broken, found))
    assert arq.jobs == [("ingest_paper", str(found_id))]


async def test_a_held_arxiv_copy_is_skipped_marked_checked_and_leaves_no_event(session, discovery_fakes, monkeypatch):
    paper = await held(session, doi="10.1/x")
    paper.pdf_check_result = "none"
    await session.commit()

    async def in_library(*_args):
        raise discovery.Conflict(discovery.ALREADY_IN_LIBRARY, paper_id="x")

    monkeypatch.setattr(discovery, "find_pdf", in_library)
    outcome = await pdf_recheck.recheck(session, discovery_fakes.providers, paper.id, NOW)

    await session.refresh(paper)
    assert outcome == "skipped"
    assert (paper.pdf_checked_at, paper.pdf_check_result) == (NOW, "none")  # the last real result stays
    assert await paper_events.history(session, paper.id) == []


async def test_due_skips_recent_papers_and_caps_oldest_first(session, monkeypatch):
    monkeypatch.setattr(pdf_recheck, "RECHECK_CAP", 3)
    await session.execute(delete(PaperEvent))
    await session.execute(delete(Paper))
    recent = await held(session, "Recent")
    recent.pdf_checked_at = NOW - timedelta(days=6)
    has_pdf = Paper(title="Has file", file_path="/x.pdf", status="ready")
    session.add(has_pdf)
    old = [await held(session, f"Old {i}") for i in range(4)]
    for age, paper in zip((30, 10, 20, 8), old):
        paper.pdf_checked_at = NOW - timedelta(days=age)
    fresh = await held(session, "Never")
    await session.commit()

    assert await pdf_recheck.due(session, NOW) == [fresh.id, old[0].id, old[2].id]


async def test_the_job_does_nothing_while_the_switch_is_off(session, worker_session, monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", lambda: _Shared(session))
    paper = await held(session)
    session.add(PaperSources(id=True, pdf_recheck_enabled=False))
    await session.commit()

    assert await worker.recheck_free_pdfs({}) == "disabled"

    await session.refresh(paper)
    assert paper.pdf_checked_at is None


async def test_the_job_runs_while_the_switch_is_on(session, worker_session, monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", lambda: _Shared(session))
    ran = []

    async def run(session_, providers, now):
        ran.append(now)
        return {"found": 0}

    monkeypatch.setattr(pdf_recheck, "run", run)
    assert await worker.recheck_free_pdfs({}) == {"found": 0}
    assert len(ran) == 1


class _Shared:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_exc):
        return False


async def test_upload_and_find_routes_write_pdf_attached(app, client, session, discovery_fakes, pdf_dir):
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.providers
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    uploaded = await held(session, "Uploaded")
    found = await held(session, "Found", oa_url=f"{HOST}/copy.pdf")

    await client.post(f"/api/papers/{uploaded.id}/pdf", files={"file": ("x.pdf", PDF, "application/pdf")})
    await client.post(f"/api/papers/{found.id}/find-pdf")

    rows = [(e.paper_id, e.kind, e.detail) for e in (await session.scalars(select(PaperEvent))).all()]
    assert sorted(rows, key=str) == sorted(
        [(uploaded.id, "pdf_attached", {"how": "manual"}), (found.id, "pdf_attached", {"how": "imported"})], key=str
    )


async def test_events_found_pdfs_and_seen_routes(client, session):
    await session.execute(delete(PaperEvent))
    a, b = await held(session, "Alpha"), await held(session, "Beta")
    await paper_events.record(session, a.id, "pdf_found", {"url": "https://x/a.pdf", "how": "imported"})
    await paper_events.record(session, b.id, "pdf_found", {"url": None, "how": "imported"})
    await paper_events.record(session, a.id, "pdf_attached", {"how": "manual"})

    notice = await client.get("/api/papers/found-pdfs")
    history = await client.get(f"/api/papers/{a.id}/events")
    unknown = await client.get("/api/papers/00000000-0000-0000-0000-000000000000/events")
    seen = await client.post("/api/papers/found-pdfs/seen")
    after = await client.get("/api/papers/found-pdfs")

    assert [(f["title"], f["paper_id"]) for f in notice.json()] == [("Beta", str(b.id)), ("Alpha", str(a.id))]
    assert [(e["kind"], e["detail"]) for e in history.json()] == [
        ("pdf_attached", {"how": "manual"}),
        ("pdf_found", {"url": "https://x/a.pdf", "how": "imported"}),
    ]
    assert (unknown.status_code, seen.status_code, after.json()) == (404, 204, [])
    assert (await client.get(f"/api/papers/{a.id}/events")).json()[0]["kind"] == "pdf_attached"
