import pytest
from sqlalchemy import select

from app.core.candidates import Candidate
from app.models import ExternalRef
from app.workers.harvest import harvest_ingest_candidate

pytestmark = pytest.mark.anyio


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
