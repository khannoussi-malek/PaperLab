"""R20/R21: the weekly free-copy re-check, its switch, paper events and the Found PDFs routes."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_discovery
from app.core import discovery, paper_events, papers, pdf_recheck, queue
from app.models import Paper, PaperEvent, PaperSources
from app.workers import pdf_recheck as worker
from app.workers.settings import WorkerSettings

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

    outcome = await pdf_recheck.recheck(session, discovery_fakes.providers, paper.id)

    await session.refresh(paper)
    assert outcome == "found"
    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert paper.pdf_check_result == "found"  # the time is set when the run claims it (due)
    assert arq.jobs == [("ingest_paper", str(paper.id))]
    events = {e.kind: e.detail for e in await paper_events.history(session, paper.id)}
    assert events == {"pdf_found": {"url": f"{HOST}/copy.pdf", "how": "imported"}, "pdf_attached": {"how": "imported"}}


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


async def test_a_held_arxiv_copy_records_none_and_waits_the_normal_week(session, discovery_fakes, monkeypatch):
    await session.execute(delete(Paper))
    paper = await held(session, doi="10.1/x")
    paper_id = paper.id
    lookups = []

    async def in_library(_session, _providers, candidate):
        lookups.append(candidate.paper_id)
        raise discovery.Conflict(discovery.ALREADY_IN_LIBRARY, paper_id="x")

    monkeypatch.setattr(discovery, "find_pdf", in_library)
    counts = await pdf_recheck.run(session, discovery_fakes.providers, NOW)
    again = await pdf_recheck.run(session, discovery_fakes.providers, NOW + timedelta(days=6))

    await session.refresh(paper)
    assert (counts["none"], sum(again.values()), lookups) == (1, 0, [paper_id])
    assert (paper.pdf_checked_at, paper.pdf_check_result) == (NOW, "none")
    assert await paper_events.history(session, paper_id) == []
    assert await pdf_recheck.due(session, NOW + timedelta(days=7, seconds=1)) == [paper_id]


async def _seed_due(session):
    await session.execute(delete(PaperEvent))
    await session.execute(delete(Paper))
    recent = await held(session, "Recent")
    recent.pdf_checked_at = NOW - timedelta(days=6)
    session.add(Paper(title="Has file", file_path="/x.pdf", status="ready"))
    old = [await held(session, f"Old {i}") for i in range(4)]
    for age, paper in zip((30, 10, 20, 8), old):
        paper.pdf_checked_at = NOW - timedelta(days=age)
    fresh = await held(session, "Never")
    await session.commit()
    return recent.id, [p.id for p in old], fresh.id


async def test_due_skips_papers_checked_in_the_last_week_and_those_with_a_pdf(session):
    recent, old, fresh = await _seed_due(session)

    found = await pdf_recheck.due(session, NOW)  # the cap (25) is far above the 5 due papers

    assert recent not in found
    assert found == [fresh, old[0], old[2], old[1], old[3]]


async def test_due_caps_and_takes_the_longest_unchecked_first(session, monkeypatch):
    monkeypatch.setattr(pdf_recheck, "RECHECK_CAP", 3)
    _recent, old, fresh = await _seed_due(session)

    assert await pdf_recheck.due(session, NOW) == [fresh, old[0], old[2]]


async def test_due_claims_its_papers_so_a_second_run_the_same_moment_takes_nothing_new(session):
    await session.execute(delete(Paper))
    ids = {(await held(session, title)).id for title in ("A", "B", "C")}

    first = await pdf_recheck.due(session, NOW)
    second = await pdf_recheck.due(session, NOW)

    assert (set(first), second) == (ids, [])
    stamped = await session.scalars(select(Paper.pdf_checked_at).where(Paper.id.in_(ids)))
    assert set(stamped) == {NOW}  # claimed: checked-at is set before any lookup


async def test_two_sessions_claim_disjoint_papers(session, monkeypatch):
    monkeypatch.setattr(pdf_recheck, "RECHECK_CAP", 2)
    await session.execute(delete(Paper))
    ids = {(await held(session, title)).id for title in ("A", "B", "C", "D", "E")}
    other = AsyncSession(bind=session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint")

    try:
        mine, theirs = await pdf_recheck.due(session, NOW), await pdf_recheck.due(other, NOW)
    finally:
        await other.close()

    assert len(mine) == len(theirs) == 2 and not set(mine) & set(theirs) and set(mine) | set(theirs) < ids


def test_the_cron_never_runs_at_startup():
    """Each worker start would otherwise check another RECHECK_CAP papers: one run a day, at 05:00."""
    [job] = [j for j in WorkerSettings.cron_jobs if j.name == "recheck_free_pdfs"]
    assert (job.run_at_startup, job.hour, job.minute) == (False, {5}, {0})


async def test_run_pauses_between_papers_only(session, discovery_fakes, monkeypatch):
    pauses = []

    async def record_pause(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(pdf_recheck, "sleep", record_pause)
    await session.execute(delete(Paper))
    for title in ("A", "B", "C"):
        await held(session, title)

    await pdf_recheck.run(session, discovery_fakes.providers, NOW)

    assert pauses == [3.0, 3.0]


async def test_a_failing_mark_is_logged_and_the_run_goes_on(session, discovery_fakes, monkeypatch):
    await session.execute(delete(Paper))
    first, second = await held(session, "First"), await held(session, "Second")
    first_id, second_id = first.id, second.id
    real = pdf_recheck._mark

    async def mark(session_, paper_id, outcome):
        if paper_id == first_id:
            raise RuntimeError("db down")
        await real(session_, paper_id, outcome)

    monkeypatch.setattr(pdf_recheck, "_mark", mark)
    counts = await pdf_recheck.run(session, discovery_fakes.providers, NOW)

    results = {p.id: p.pdf_check_result for p in await session.scalars(select(Paper))}
    assert sum(counts.values()) == 2
    assert (results[first_id], results[second_id]) == (None, "none")


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


async def test_switching_off_mid_run_stops_the_rest(session, discovery_fakes, monkeypatch):
    await session.execute(delete(PaperSources))
    await session.execute(delete(Paper))
    for title in ("A", "B", "C"):
        await held(session, title)
    real, looked = discovery.find_pdf, []

    async def then_switch_off(session_, providers, candidate):
        looked.append(candidate.paper_id)
        await session_.execute(update(PaperSources).values(pdf_recheck_enabled=False))
        return await real(session_, providers, candidate)

    session.add(PaperSources(id=True, pdf_recheck_enabled=True))
    await session.commit()
    monkeypatch.setattr(discovery, "find_pdf", then_switch_off)
    counts = await pdf_recheck.run(session, discovery_fakes.providers, NOW)

    assert (len(looked), sum(counts.values())) == (1, 1)


class _Shared:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_exc):
        return False


async def test_a_failing_pdf_found_write_still_leaves_the_ingest_queued(
    session, arq, discovery_fakes, pdf_dir, monkeypatch
):
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    paper = await held(session, "Found", oa_url=f"{HOST}/copy.pdf")
    paper_id = paper.id

    async def broken(*_args):
        raise RuntimeError("event write failed")

    monkeypatch.setattr(paper_events, "record", broken)
    outcome = await pdf_recheck.recheck(session, discovery_fakes.providers, paper_id)

    assert outcome == "found" and arq.jobs == [("ingest_paper", str(paper_id))]


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


async def _event(session, paper, kind, detail, created_at) -> PaperEvent:
    event = PaperEvent(paper_id=paper.id, kind=kind, detail=detail, created_at=created_at)
    session.add(event)
    await session.commit()
    return event


async def test_events_found_pdfs_and_seen_routes(client, session):
    await session.execute(delete(PaperEvent))
    a, b = await held(session, "Alpha"), await held(session, "Beta")
    t = NOW - timedelta(hours=3)
    shown_a = await _event(session, a, "pdf_found", {"url": "https://x/a.pdf", "how": "imported"}, t)
    shown_b = await _event(session, b, "pdf_found", {"url": None, "how": "imported"}, t + timedelta(hours=1))
    await _event(session, a, "pdf_attached", {"how": "manual"}, t + timedelta(hours=2))

    notice = await client.get("/api/papers/found-pdfs")
    history = await client.get(f"/api/papers/{a.id}/events")
    unknown = await client.get("/api/papers/00000000-0000-0000-0000-000000000000/events")
    late = await _event(session, b, "pdf_found", {"url": None, "how": "imported"}, t + timedelta(hours=3))
    seen = await client.post("/api/papers/found-pdfs/seen", json={"ids": [f["id"] for f in notice.json()]})
    after = await client.get("/api/papers/found-pdfs")

    assert [(f["id"], f["title"], f["paper_id"]) for f in notice.json()] == [
        (str(shown_b.id), "Beta", str(b.id)),
        (str(shown_a.id), "Alpha", str(a.id)),
    ]
    assert [(e["kind"], e["detail"]) for e in history.json()] == [
        ("pdf_attached", {"how": "manual"}),
        ("pdf_found", {"url": "https://x/a.pdf", "how": "imported"}),
    ]
    assert (unknown.status_code, seen.status_code) == (404, 204)
    assert [f["id"] for f in after.json()] == [str(late.id)]  # arrived after the list: stays unseen
