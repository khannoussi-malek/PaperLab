"""Deciding on the desk (app/core/triage.py): the pile mapping, reasons, the locked write, retries."""

import asyncio
import uuid

import pytest
from conftest import TEST_DATABASE_URL
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import papers, triage
from app.core.errors import Gone, InvalidInput, NotFound
from app.models import Paper, PaperMerge, TriageEvent

pytestmark = pytest.mark.anyio

STARTS = [(t, p) for t in (None, "keep", "later", "drop") for p in (0, 1, 3)]
EXPECT = {  # pile -> (triage or None = unchanged, min pass or None = unchanged)
    "read_closely": ("keep", None), "skim": ("keep", 1), "later": ("later", None),
    "not_relevant": ("drop", None), "skip": (None, None),
}  # fmt: skip


@pytest.mark.parametrize("pile", list(EXPECT))
@pytest.mark.parametrize(("t", "p"), STARTS)
def test_apply_pile_table(pile, t, p):
    want_t, min_pass = EXPECT[pile]
    assert triage.apply_pile(pile, t, p) == (want_t or t, p if min_pass is None else max(p, min_pass))


def test_skim_never_lowers_and_read_closely_keeps_zero():
    assert triage.apply_pile("skim", "later", 3) == ("keep", 3)
    assert triage.apply_pile("skim", None, 0) == ("keep", 1)
    assert triage.apply_pile("read_closely", None, 0) == ("keep", 0)


def test_apply_pile_unknown():
    with pytest.raises(InvalidInput) as e:
        triage.apply_pile("bogus", None, 0)
    assert str(e.value) == "unknown_pile"
    assert "skim" in e.value.details["allowed"]


async def make(session, **kw) -> Paper:
    paper = Paper(title="P", **kw)
    session.add(paper)
    await session.commit()
    return paper


async def count(session, paper_id) -> int:
    return await session.scalar(select(func.count()).select_from(TriageEvent).where(TriageEvent.paper_id == paper_id))


async def reread(session, paper_id) -> Paper:
    return await papers.get_paper(session, paper_id, lock=True)


@pytest.mark.parametrize("pile", list(EXPECT))
async def test_decide_writes_event_and_paper(session, pile):
    paper = await make(session, triage="later", reading_pass=0)
    reason = {"not_relevant": "off_topic"}.get(pile)
    sid = uuid.uuid4()
    got, event, replayed = await triage.decide(session, paper.id, pile=pile, session_id=sid, reason=reason, fivecs=5)
    want = triage.apply_pile(pile, "later", 0)
    assert replayed is False
    assert (event.before_triage, event.before_pass) == ("later", 0)
    assert (event.after_triage, event.after_pass) == want
    assert (event.source, event.pile, event.session_id, event.fivecs) == ("desk", pile, sid, 5)
    fresh = await reread(session, paper.id)
    assert (fresh.triage, fresh.reading_pass) == want == (got.triage, got.reading_pass)
    assert await count(session, paper.id) == 1


async def test_skip_changes_nothing_but_logs(session):
    paper = await make(session, triage="keep", reading_pass=2)
    _, event, _ = await triage.decide(session, paper.id, pile="skip", session_id=uuid.uuid4())
    assert (event.before_triage, event.before_pass) == (event.after_triage, event.after_pass) == ("keep", 2)


async def test_drop_needs_a_reason_and_writes_nothing(session):
    paper = await make(session)
    with pytest.raises(InvalidInput) as e:
        await triage.decide(session, paper.id, pile="not_relevant", session_id=uuid.uuid4())
    assert str(e.value) == "reason_required"
    assert await count(session, paper.id) == 0


async def test_reason_from_another_pile(session):
    paper = await make(session)
    with pytest.raises(InvalidInput) as e:
        await triage.decide(session, paper.id, pile="skim", session_id=uuid.uuid4(), reason="off_topic")
    assert str(e.value) == "unknown_reason"
    assert e.value.details["allowed"] == list(triage.REASONS["skim"])


async def test_other_without_note_is_fine(session):
    paper = await make(session)
    _, event, _ = await triage.decide(session, paper.id, pile="not_relevant", session_id=uuid.uuid4(), reason="other")
    assert event.note is None


async def test_note_length(session):
    paper = await make(session)
    ok = await triage.decide(session, paper.id, pile="skip", session_id=uuid.uuid4(), note="x" * 500)
    assert len(ok[1].note) == 500
    with pytest.raises(InvalidInput) as e:
        await triage.decide(session, paper.id, pile="skip", session_id=uuid.uuid4(), note="x" * 501)
    assert str(e.value) == "note_too_long"


async def test_unknown_paper(session):
    with pytest.raises(NotFound):
        await triage.decide(session, uuid.uuid4(), pile="skip", session_id=uuid.uuid4())


async def test_merged_paper_is_gone(session):
    kept, gone = uuid.uuid4(), uuid.uuid4()
    session.add(PaperMerge(kept_id=kept, merged_id=gone, status="merged"))
    await session.commit()
    with pytest.raises(Gone) as e:
        await triage.decide(session, gone, pile="skip", session_id=uuid.uuid4())
    assert e.value.details["kept_id"] == str(kept)


async def test_replay_returns_first_event_and_changes_nothing(session):
    paper = await make(session)
    sid, cid = uuid.uuid4(), uuid.uuid4()
    _, first, _ = await triage.decide(session, paper.id, pile="skim", session_id=sid, client_id=cid)
    await session.execute(Paper.__table__.update().where(Paper.id == paper.id).values(triage="drop", reading_pass=0))
    await session.commit()
    got, again, replayed = await triage.decide(session, paper.id, pile="later", session_id=sid, client_id=cid)
    assert replayed is True
    assert again.id == first.id
    assert (got.triage, got.reading_pass) == ("drop", 0)
    assert await count(session, paper.id) == 1


async def test_two_concurrent_identical_posts_make_one_event():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    sid, cid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as s0:
        paper = await make(s0, triage="later")
    try:

        async def post():
            async with AsyncSession(engine, expire_on_commit=False) as s:
                return await triage.decide(s, paper.id, pile="skim", session_id=sid, client_id=cid)

        results = await asyncio.gather(post(), post())
        assert sorted(r[2] for r in results) == [False, True]
        assert results[0][1].id == results[1][1].id
        async with AsyncSession(engine) as s:
            assert await count(s, paper.id) == 1
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(delete(TriageEvent).where(TriageEvent.paper_id == paper.id))
            await s.execute(delete(Paper).where(Paper.id == paper.id))
            await s.commit()
        await engine.dispose()


async def test_a_drop_leaves_the_paper_listed(session):
    paper = await make(session)
    await triage.decide(session, paper.id, pile="not_relevant", session_id=uuid.uuid4(), reason="duplicate")
    assert paper.id in {p.id for p in await papers.list_papers(session)}
