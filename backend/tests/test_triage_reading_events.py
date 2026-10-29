"""set_reading leaves one history event per real change and takes the papers row lock (D119)."""

import asyncio
import uuid

import pytest
from conftest import TEST_DATABASE_URL
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import papers, triage
from app.core.errors import InvalidInput
from app.models import Paper, TriageEvent

pytestmark = pytest.mark.anyio


async def make(session, **kw) -> Paper:
    paper = Paper(title="P", **kw)
    session.add(paper)
    await session.commit()
    return paper


async def events(session, paper) -> list[TriageEvent]:
    rows = await session.scalars(
        select(TriageEvent).where(TriageEvent.paper_id == paper.id).order_by(TriageEvent.created_at, TriageEvent.id)
    )
    return list(rows)


async def test_a_reader_change_writes_one_event(session):
    paper = await make(session)
    await papers.set_reading(session, paper.id, {"triage": "keep"})
    (e,) = await events(session, paper)
    assert (e.source, e.before_triage, e.before_pass, e.after_triage, e.after_pass) == ("reader", None, 0, "keep", 0)
    assert (e.pile, e.session_id, e.reason) == (None, None, None)


async def test_the_library_source_is_recorded(session):
    paper = await make(session)
    await papers.set_reading(session, paper.id, {"reading_pass": 2}, source="library")
    (e,) = await events(session, paper)
    assert (e.source, e.after_pass) == ("library", 2)


async def test_both_fields_in_one_call_make_one_event(session):
    paper = await make(session)
    await papers.set_reading(session, paper.id, {"triage": "later", "reading_pass": 1})
    (e,) = await events(session, paper)
    assert (e.after_triage, e.after_pass) == ("later", 1)


async def test_setting_what_the_paper_already_has_writes_nothing(session):
    paper = await make(session, triage="keep", reading_pass=1)
    got = await papers.set_reading(session, paper.id, {"triage": "keep", "reading_pass": 1})
    assert got.id == paper.id
    assert await events(session, paper) == []


@pytest.mark.parametrize(
    ("changes", "code"),
    [({"reading_pass": 4}, "reading_pass_out_of_range"), ({"triage": "maybe"}, "unknown_triage")],
)
async def test_a_failed_validation_leaves_no_event(session, changes, code):
    paper = await make(session)
    with pytest.raises(InvalidInput) as e:
        await papers.set_reading(session, paper.id, changes)
    assert str(e.value) == code
    assert await events(session, paper) == []


async def test_an_unknown_source_raises_before_any_event(session):
    paper = await make(session)
    with pytest.raises(InvalidInput) as e:
        await papers.set_reading(session, paper.id, {"triage": "keep"}, source="desk")
    assert str(e.value) == "unknown_source"
    assert await events(session, paper) == []


async def test_manual_fields_stay_untouched(session):
    paper = await make(session)
    before = list(paper.manual_fields or [])
    got = await papers.set_reading(session, paper.id, {"triage": "keep"})
    assert list(got.manual_fields or []) == before


@pytest.fixture
def slow_first_lock(monkeypatch):
    """The first get_paper call sets `held` once it has read the paper, then keeps its transaction open a moment, so
    a second session started on `held` always collides with it."""
    real, calls, held = papers.get_paper, [], asyncio.Event()

    async def slow(session, paper_id, **kw):
        paper = await real(session, paper_id, **kw)
        calls.append(1)
        if len(calls) == 1:
            held.set()
            await asyncio.sleep(0.4)
        return paper

    monkeypatch.setattr(papers, "get_paper", slow)
    return held


async def test_set_reading_and_decide_racing_chain_their_events(slow_first_lock):
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as s0:
        paper = await make(s0)
    try:

        async def reader():
            async with AsyncSession(engine, expire_on_commit=False) as s:
                await papers.set_reading(s, paper.id, {"triage": "later"})

        async def desk():
            await slow_first_lock.wait()
            async with AsyncSession(engine, expire_on_commit=False) as s:
                await triage.decide(s, paper.id, pile="skim", session_id=uuid.uuid4())

        await asyncio.gather(reader(), desk())
        async with AsyncSession(engine) as s:
            first, second = await events(s, paper)
            final = await s.get(Paper, paper.id, populate_existing=True)
            assert (first.source, second.source) == ("reader", "desk")
            assert (second.before_triage, second.before_pass) == (first.after_triage, first.after_pass)
            assert (final.triage, final.reading_pass) == (second.after_triage, second.after_pass)
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(delete(TriageEvent).where(TriageEvent.paper_id == paper.id))
            await s.execute(delete(Paper).where(Paper.id == paper.id))
            await s.commit()
        await engine.dispose()
