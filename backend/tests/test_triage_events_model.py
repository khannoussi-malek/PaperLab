"""triage_events (0060): the CHECKs and indexes refuse bad rows; an event goes with its paper."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.anyio

COLUMNS = "paper_id, source, pile, before_triage, after_triage, before_pass, after_pass"


async def paper(session) -> uuid.UUID:
    return (await session.execute(text("INSERT INTO papers (title) VALUES ('P') RETURNING id"))).scalar_one()


async def event(session, paper_id, **over) -> uuid.UUID:
    """Insert one event; `over` replaces defaults (a desk skim, later -> keep, pass 0 -> 1)."""
    row = {
        "paper_id": paper_id, "source": "desk", "pile": "skim", "before_triage": "later", "after_triage": "keep",
        "before_pass": 0, "after_pass": 1, "reason": None, "note": None, "fivecs": None, "pdf_ms": None,
        "card_ms": None, "session_id": None, "client_id": None, "undone_event_id": None,
    }  # fmt: skip
    row.update(over)
    cols = ", ".join(row)
    marks = ", ".join(f":{c}" for c in row)
    return (
        await session.execute(text(f"INSERT INTO triage_events ({cols}) VALUES ({marks}) RETURNING id"), row)
    ).scalar_one()


async def refuses(session, paper_id, **over):
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await event(session, paper_id, **over)


async def test_a_desk_drop_needs_a_reason(session):
    p = await paper(session)
    await refuses(session, p, pile="not_relevant")
    await event(session, p, pile="not_relevant", reason="off topic")
    await event(session, p)


async def test_an_undo_row_names_what_it_undoes(session):
    p = await paper(session)
    first = await event(session, p)
    await event(session, p, source="undo", pile=None, undone_event_id=first)
    await refuses(session, p, source="undo", pile=None)
    await refuses(session, p, undone_event_id=first)


async def test_two_undos_of_one_event_fail(session):
    p = await paper(session)
    first = await event(session, p)
    await event(session, p, source="undo", pile=None, undone_event_id=first)
    await refuses(session, p, source="undo", pile=None, undone_event_id=first)


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "mail"}, {"pile": "cite_later"}, {"before_triage": "maybe"}, {"after_triage": "maybe"},
        {"before_pass": 4}, {"after_pass": -1}, {"fivecs": 32}, {"pdf_ms": -1}, {"card_ms": -1}, {"note": "x" * 501},
    ],
)  # fmt: skip
async def test_every_column_check_refuses(session, bad):
    await refuses(session, await paper(session), **bad)


async def test_the_edges_pass(session):
    p = await paper(session)
    await event(session, p, before_pass=3, after_pass=0, fivecs=31, pdf_ms=0, card_ms=0, note="x" * 500)


async def test_a_retry_key_is_unique_per_session(session):
    p = await paper(session)
    s1, s2, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await event(session, p, session_id=s1, client_id=c)
    await refuses(session, p, session_id=s1, client_id=c)
    await event(session, p, session_id=s2, client_id=c)
    await event(session, p, session_id=s1)
    await event(session, p, session_id=s1)


async def test_deleting_a_paper_removes_its_events_and_undo_pair(session):
    p = await paper(session)
    first = await event(session, p)
    await event(session, p, source="undo", pile=None, undone_event_id=first)
    await session.execute(text("DELETE FROM papers WHERE id = :p"), {"p": p})
    left = (
        await session.execute(text("SELECT count(*) FROM triage_events WHERE paper_id = :p"), {"p": p})
    ).scalar_one()
    assert left == 0


async def test_the_pile_goes_with_the_desk(session):
    p = await paper(session)
    await refuses(session, p, pile=None)
    await refuses(session, p, source="reader")
    await refuses(session, p, source="library")
    await event(session, p, source="reader", pile=None)
