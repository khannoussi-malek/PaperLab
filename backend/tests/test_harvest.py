from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.core.candidates import Candidate
from app.models import ExternalRef
from app.workers.harvest import harvest_ingest_candidate

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def _reuse_test_session(session):
    yield session  # never closes it -- the `session` fixture's own teardown does that


async def test_a_new_candidate_is_inserted(session):
    candidate = Candidate(
        title="A New Eprint", authors=["Ada Fixture"], year=2026, external_ids={"iacr_eprint": "2026/9001"},
        abstract="An abstract.", sources=("iacr_eprint",),
    )

    await harvest_ingest_candidate(session, candidate)
    await session.flush()

    row = (
        await session.execute(select(ExternalRef).where(ExternalRef.external_ids["iacr_eprint"].astext == "2026/9001"))
    ).scalar_one()
    assert row.title == "A New Eprint"
    assert row.sources == ["iacr_eprint"]


async def test_a_revised_eprint_updates_the_existing_row_not_a_duplicate(session):
    first = Candidate(
        title="Version One", authors=[], year=2026, external_ids={"iacr_eprint": "2026/9002"}, sources=("iacr_eprint",),
    )
    await harvest_ingest_candidate(session, first)
    await session.flush()

    revised = Candidate(
        title="Version Two (revised)", authors=["New Author"], year=2026,
        external_ids={"iacr_eprint": "2026/9002"}, sources=("iacr_eprint",),
    )
    await harvest_ingest_candidate(session, revised)
    await session.flush()

    rows = (
        await session.execute(select(ExternalRef).where(ExternalRef.external_ids["iacr_eprint"].astext == "2026/9002"))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Version Two (revised)"
    assert rows[0].authors == ["New Author"]


def test_harvest_iacr_eprint_is_registered_as_a_cron_job():
    from app.workers.settings import WorkerSettings

    names = {job.name for job in WorkerSettings.cron_jobs}
    assert "harvest_iacr_eprint" in names


async def test_running_the_harvest_twice_does_not_duplicate_rows(session, monkeypatch):
    from app.providers import iacr_eprint
    from app.workers import harvest

    call_count = 0

    async def fake_fetch_page(http, *, from_date=None, until_date=None, resumption_token=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{"identifier": "oai:eprint.iacr.org:2026/5001", "datestamp": "2026-01-01T00:00:00Z",
                      "title": "Only Paper", "creators": [], "description": None}], None
        return [], None  # second run: nothing new since last_synced_at

    monkeypatch.setattr(iacr_eprint, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(harvest, "SessionLocal", lambda: _reuse_test_session(session))

    await harvest.harvest_iacr_eprint({})
    await harvest.harvest_iacr_eprint({})

    from sqlalchemy import select

    from app.models import ExternalRef

    rows = (
        await session.execute(select(ExternalRef).where(ExternalRef.external_ids["iacr_eprint"].astext == "2026/5001"))
    ).scalars().all()
    assert len(rows) == 1
    assert call_count == 2  # the second run made exactly one fetch_page call, not a full re-harvest


async def test_the_harvest_follows_a_multi_page_resumption_chain_to_completion(session, monkeypatch):
    from app.providers import iacr_eprint
    from app.workers import harvest

    pages = [
        ([{"identifier": "oai:eprint.iacr.org:2026/6001", "datestamp": "2026-01-01T00:00:00Z", "title": "Page 1",
           "creators": [], "description": None}], "token-page-2"),
        ([{"identifier": "oai:eprint.iacr.org:2026/6002", "datestamp": "2026-01-01T00:00:00Z", "title": "Page 2",
           "creators": [], "description": None}], None),
    ]
    calls = iter(pages)

    async def fake_fetch_page(http, *, from_date=None, until_date=None, resumption_token=None):
        return next(calls)

    monkeypatch.setattr(iacr_eprint, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(harvest, "SessionLocal", lambda: _reuse_test_session(session))

    await harvest.harvest_iacr_eprint({})

    from sqlalchemy import select

    from app.models import ExternalRef

    rows = (
        await session.execute(select(ExternalRef).where(ExternalRef.external_ids["iacr_eprint"].astext.isnot(None)))
    ).scalars().all()
    assert {r.external_ids["iacr_eprint"] for r in rows} == {"2026/6001", "2026/6002"}
