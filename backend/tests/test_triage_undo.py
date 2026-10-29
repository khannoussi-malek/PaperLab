"""Undo, late reason, history and the session summary (app/core/triage.py)."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from conftest import TEST_DATABASE_URL
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import papers, triage
from app.core.errors import Conflict, Gone, InvalidInput, NotFound
from app.models import Paper, PaperMerge, TriageEvent

pytestmark = pytest.mark.anyio

PILES = ["read_closely", "skim", "later", "not_relevant"]


async def make(session, **kw) -> Paper:
    paper = Paper(title="P", **kw)
    session.add(paper)
    await session.commit()
    return paper


async def count(session, paper_id) -> int:
    return await session.scalar(select(func.count()).select_from(TriageEvent).where(TriageEvent.paper_id == paper_id))


async def desk(session, paper, pile, sid=None, **kw):
    reason = "off_topic" if pile == "not_relevant" else None
    _, event, _ = await triage.decide(session, paper.id, pile=pile, session_id=sid or uuid.uuid4(), reason=reason, **kw)
    return event


async def state(session, paper_id):
    paper = await papers.get_paper(session, paper_id, lock=True)
    return paper.triage, paper.reading_pass


@pytest.mark.parametrize("pile", PILES)
async def test_undo_restores_exact_before_state(session, pile):
    paper = await make(session, triage="drop", reading_pass=2)
    event = await desk(session, paper, pile)
    got, undo = await triage.undo(session, event.id)
    assert (got.triage, got.reading_pass) == ("drop", 2) == await state(session, paper.id)
    assert (undo.source, undo.pile, undo.undone_event_id) == ("undo", None, event.id)
    assert (undo.before_triage, undo.before_pass) == (event.after_triage, event.after_pass)
    assert (undo.after_triage, undo.after_pass) == ("drop", 2)


async def test_two_undos_in_reverse_order_walk_back(session):
    paper = await make(session, triage=None, reading_pass=0)
    first = await desk(session, paper, "later")
    second = await desk(session, paper, "skim")
    await triage.undo(session, second.id)
    assert await state(session, paper.id) == ("later", 0)
    await triage.undo(session, first.id)
    assert await state(session, paper.id) == (None, 0)


@pytest.mark.parametrize("change", [{"triage": "drop"}, {"reading_pass": 3}])
async def test_changed_since_writes_nothing(session, change):
    paper = await make(session)
    event = await desk(session, paper, "skim")
    await papers.set_reading(session, paper.id, change)
    before = await count(session, paper.id)
    with pytest.raises(Conflict) as e:
        await triage.undo(session, event.id)
    assert str(e.value) == "changed_since"
    assert await count(session, paper.id) == before


async def test_changed_since_after_a_merge_changed_the_kept_state(session):
    paper = await make(session)
    event = await desk(session, paper, "later")
    await session.execute(update(Paper).where(Paper.id == paper.id).values(triage="keep", reading_pass=2))
    await session.commit()
    with pytest.raises(Conflict) as e:
        await triage.undo(session, event.id)
    assert str(e.value) == "changed_since"


async def test_a_to_b_to_a_counts_as_unchanged_and_undoes(session):
    # documented: only the state is compared, not what happened in between
    paper = await make(session, triage="later")
    event = await desk(session, paper, "skim")  # later,0 -> keep,1
    await papers.set_reading(session, paper.id, {"triage": "drop"})
    await papers.set_reading(session, paper.id, {"triage": "keep"})
    await triage.undo(session, event.id)
    assert await state(session, paper.id) == ("later", 0)


async def test_already_undone(session):
    paper = await make(session)
    event = await desk(session, paper, "skim")
    await triage.undo(session, event.id)
    with pytest.raises(Conflict) as e:
        await triage.undo(session, event.id)
    assert str(e.value) == "already_undone"


async def test_racing_undos_one_wins():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as s0:
        paper = await make(s0)
        event = await desk(s0, paper, "skim")
    try:

        async def go():
            async with AsyncSession(engine, expire_on_commit=False) as s:
                return await triage.undo(s, event.id)

        results = await asyncio.gather(go(), go(), return_exceptions=True)
        wins = [r for r in results if not isinstance(r, Exception)]
        fails = [r for r in results if isinstance(r, Exception)]
        assert len(wins) == 1 and len(fails) == 1
        assert isinstance(fails[0], Conflict) and str(fails[0]) == "already_undone"
        async with AsyncSession(engine) as s:
            n = await s.scalar(
                select(func.count()).select_from(TriageEvent).where(TriageEvent.undone_event_id == event.id)
            )
            assert n == 1
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(delete(TriageEvent).where(TriageEvent.paper_id == paper.id))
            await s.execute(delete(Paper).where(Paper.id == paper.id))
            await s.commit()
        await engine.dispose()


async def test_not_a_desk_event(session):
    paper = await make(session)
    reader = triage.log_change(session, paper, source="reader", before=(None, 0), after=(None, 1))
    desk_event = await desk(session, paper, "skim")
    _, undo = await triage.undo(session, desk_event.id)
    await session.commit()
    for target in (reader, undo):
        with pytest.raises(Conflict) as e:
            await triage.undo(session, target.id)
        assert str(e.value) == "not_a_desk_event"


async def test_undoing_a_skip_writes_only_an_undo_row(session):
    paper = await make(session, triage="keep", reading_pass=2)
    event = await desk(session, paper, "skip")
    _, undo = await triage.undo(session, event.id)
    assert (undo.before_triage, undo.before_pass, undo.after_triage, undo.after_pass) == ("keep", 2, "keep", 2)
    assert await state(session, paper.id) == ("keep", 2)
    assert await count(session, paper.id) == 2


async def test_unknown_event(session):
    with pytest.raises(NotFound) as e:
        await triage.undo(session, uuid.uuid4())
    assert str(e.value) == "unknown_event"


async def test_add_reason_fills_reason_and_note(session):
    paper = await make(session)
    event = await desk(session, paper, "skim")
    got = await triage.add_reason(session, event.id, reason="related_work", note="cite it")
    assert (got.reason, got.note) == ("related_work", "cite it")
    assert (await triage.add_reason(session, event.id, note="only note")).reason == "related_work"


async def test_add_reason_window(session):
    paper = await make(session)
    event = await desk(session, paper, "skim")
    ok = event.created_at + timedelta(minutes=9)
    late = event.created_at + timedelta(minutes=11)
    await triage.add_reason(session, event.id, reason="related_work", now=ok)
    with pytest.raises(Conflict) as e:
        await triage.add_reason(session, event.id, reason="related_work", now=late)
    assert str(e.value) == "late_reason_window"


async def test_add_reason_refusals(session):
    paper = await make(session)
    event = await desk(session, paper, "skim")
    reader = triage.log_change(session, paper, source="reader", before=(None, 0), after=(None, 1))
    await session.commit()
    with pytest.raises(Conflict) as e:
        await triage.add_reason(session, reader.id, reason="related_work")
    assert str(e.value) == "not_a_desk_event"
    for kw, code in [
        ({"reason": "off_topic"}, "unknown_reason"),
        ({"note": "x" * 501}, "note_too_long"),
        ({}, "reason_required"),
    ]:
        with pytest.raises(InvalidInput) as e:
            await triage.add_reason(session, event.id, **kw)
        assert str(e.value) == code
    with pytest.raises(NotFound):
        await triage.add_reason(session, uuid.uuid4(), reason="related_work")


@pytest.mark.parametrize("kw", [{"reason": None}, {"reason": ""}])
async def test_a_drop_never_loses_its_reason(session, kw):
    paper = await make(session)
    event = await desk(session, paper, "not_relevant")
    with pytest.raises(InvalidInput) as e:
        await triage.add_reason(session, event.id, note="why", **kw)
    assert str(e.value) == "reason_required"
    assert event.reason == "off_topic"


async def test_history_newest_first_with_undo_rows(session):
    paper = await make(session)
    a = await desk(session, paper, "later")
    b = await desk(session, paper, "skim")
    _, undo = await triage.undo(session, b.id)
    now = a.created_at
    for i, ev in enumerate((a, b, undo)):  # one transaction: now() ties, so space them out
        await session.execute(
            update(TriageEvent).where(TriageEvent.id == ev.id).values(created_at=now + timedelta(seconds=i))
        )
    await session.commit()
    rows = await triage.history(session, paper.id)
    assert [r.id for r in rows] == [undo.id, b.id, a.id]


async def test_history_of_a_merged_paper_is_gone(session):
    kept, gone = uuid.uuid4(), uuid.uuid4()
    session.add(PaperMerge(kept_id=kept, merged_id=gone, status="merged"))
    await session.commit()
    with pytest.raises(Gone):
        await triage.history(session, gone)


async def test_summary_excludes_undone_and_counts_skips_apart(session):
    paper = await make(session)
    sid = uuid.uuid4()
    await desk(session, paper, "skim", sid, card_ms=1000, pdf_opened=True)
    await desk(session, paper, "skim", sid, card_ms=None)
    await desk(session, paper, "skip", sid, card_ms=300)
    await desk(session, paper, "skim", uuid.uuid4(), card_ms=9999)  # another session
    undone = await desk(session, paper, "later", sid, card_ms=500)
    await triage.undo(session, undone.id)
    assert await triage.summary(session, sid) == {
        "per_pile": {"skim": 2},
        "skipped": 1,
        "card_ms": 1300,
        "pdf_opened": 1,
        "decided": 2,
    }


async def test_summary_unknown_session_is_zeros(session):
    assert await triage.summary(session, uuid.uuid4()) == {
        "per_pile": {}, "skipped": 0, "card_ms": 0, "pdf_opened": 0, "decided": 0,
    }  # fmt: skip
