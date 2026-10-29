"""The triage desk's decisions (D119): a pile moves a paper's `triage` / `reading_pass` and appends one event."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import papers
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Paper, TriageEvent

# pile -> (triage it sets, pass it raises to at least). None: leave it alone. The one place the mapping is written.
PILES: dict[str, tuple[str | None, int | None]] = {
    "read_closely": ("keep", None),
    "skim": ("keep", 1),
    "later": ("later", None),
    "not_relevant": ("drop", None),
    "skip": (None, None),
}
REASONS: dict[str, tuple[str, ...]] = {
    "not_relevant": ("off_topic", "wrong_method", "low_quality", "duplicate", "already_known", "other"),
    "read_closely": ("core_to_my_question", "method_i_need", "key_background"),
    "skim": ("background_only", "related_work", "partly_relevant"),
    "later": ("needs_background", "maybe_relevant_later", "related_work"),
    "skip": (),
}
NOTE_MAX = 500
DESK_LATE_REASON_MINUTES = 10  # a reason may be added to a desk decision this long after it


def apply_pile(pile: str, triage: str | None, reading_pass: int) -> tuple[str | None, int]:
    """The paper's (triage, reading_pass) after `pile`. A skim never lowers the pass; skip changes nothing."""
    if pile not in PILES:
        raise InvalidInput("unknown_pile", allowed=list(PILES))
    new_triage, min_pass = PILES[pile]
    return (
        triage if new_triage is None else new_triage,
        reading_pass if min_pass is None else max(reading_pass, min_pass),
    )


def check_reason(pile: str, reason: str | None, note: str | None) -> None:
    """Raises InvalidInput: reason_required (a drop), unknown_reason (with allowed), note_too_long."""
    if reason is None and pile == "not_relevant":
        raise InvalidInput("reason_required", allowed=list(REASONS[pile]))
    if reason is not None and reason not in REASONS[pile]:
        raise InvalidInput("unknown_reason", allowed=list(REASONS[pile]))
    if note is not None and len(note) > NOTE_MAX:
        raise InvalidInput("note_too_long", max=NOTE_MAX)


def log_change(
    session: AsyncSession,
    paper: Paper,
    *,
    source: str,
    before: tuple[str | None, int],
    after: tuple[str | None, int],
    **fields,
) -> TriageEvent:
    """The one place an event row is built (added to the session, not committed). `fields`: pile, reason, note, ..."""
    event = TriageEvent(
        paper_id=paper.id,
        source=source,
        before_triage=before[0],
        before_pass=before[1],
        after_triage=after[0],
        after_pass=after[1],
        **fields,
    )
    session.add(event)
    return event


async def _stored(session: AsyncSession, session_id: uuid.UUID, client_id: uuid.UUID) -> TriageEvent | None:
    return await session.scalar(
        select(TriageEvent).where(TriageEvent.session_id == session_id, TriageEvent.client_id == client_id)
    )


async def _replay(session: AsyncSession, event: TriageEvent) -> tuple[Paper, TriageEvent, bool]:
    paper = await papers.get_paper(session, event.paper_id)
    await session.refresh(paper)  # the paper as it is now, not as this session saw it earlier
    return paper, event, True


async def decide(
    session: AsyncSession,
    paper_id: uuid.UUID,
    *,
    pile: str,
    session_id: uuid.UUID,
    client_id: uuid.UUID | None = None,
    reason: str | None = None,
    note: str | None = None,
    fivecs: int | None = None,
    pdf_opened: bool = False,
    pdf_ms: int | None = None,
    card_ms: int | None = None,
) -> tuple[Paper, TriageEvent, bool]:
    """Move a paper to a pile and record it. Returns (paper, event, replayed): a retry with the same client_id gets
    the first event back and changes nothing. Raises InvalidInput (see check_reason, apply_pile), NotFound, Gone."""
    if pile not in PILES:
        raise InvalidInput("unknown_pile", allowed=list(PILES))
    check_reason(pile, reason, note)
    if client_id is not None and (event := await _stored(session, session_id, client_id)):
        return await _replay(session, event)
    paper = await papers.get_paper(session, paper_id, lock=True)  # lock order: the papers row first
    before = (paper.triage, paper.reading_pass)
    after = apply_pile(pile, *before)
    if after != before:
        await session.execute(update(Paper).where(Paper.id == paper_id).values(triage=after[0], reading_pass=after[1]))
    event = log_change(
        session, paper, source="desk", before=before, after=after, pile=pile, session_id=session_id,
        client_id=client_id, reason=reason, note=note, fivecs=fivecs, pdf_opened=pdf_opened, pdf_ms=pdf_ms,
        card_ms=card_ms,
    )  # fmt: skip
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if client_id is not None and (event := await _stored(session, session_id, client_id)):
            return await _replay(session, event)
        raise
    await session.refresh(paper)
    return paper, event, False


async def undo(session: AsyncSession, event_id: uuid.UUID) -> tuple[Paper, TriageEvent]:
    """Put a desk decision back as it was, if the paper still sits where the decision left it. Raises NotFound
    (unknown_event), Gone, Conflict (not_a_desk_event, already_undone, changed_since)."""
    event = await session.get(TriageEvent, event_id)
    if event is None:
        raise NotFound("unknown_event")
    paper = await papers.get_paper(session, event.paper_id, lock=True)  # lock order: the papers row first
    event = await session.get(TriageEvent, event_id, populate_existing=True)
    if event is None:
        raise NotFound("unknown_event")
    if event.source != "desk":
        raise Conflict("not_a_desk_event")
    if await session.scalar(select(TriageEvent.id).where(TriageEvent.undone_event_id == event_id)):
        raise Conflict("already_undone")
    now_state = (paper.triage, paper.reading_pass)
    if now_state != (event.after_triage, event.after_pass):
        raise Conflict("changed_since")
    restored = (event.before_triage, event.before_pass)
    if restored != now_state:  # a skip moved nothing
        await session.execute(
            update(Paper).where(Paper.id == paper.id).values(triage=restored[0], reading_pass=restored[1])
        )
    undo_event = log_change(session, paper, source="undo", before=now_state, after=restored, undone_event_id=event_id)
    try:
        await session.commit()
    except IntegrityError:  # the unique index on undone_event_id is the backstop for the check above
        await session.rollback()
        raise Conflict("already_undone") from None
    await session.refresh(paper)
    return paper, undo_event


UNSET = object()  # a reason not sent, as against sent as null


async def add_reason(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    reason: str | None | object = UNSET,
    note: str | None = None,
    now: datetime | None = None,
) -> TriageEvent:
    """Fill the reason and/or note of a desk decision made less than DESK_LATE_REASON_MINUTES ago. A drop's reason
    can be changed, never removed (pass `reason` only when it was sent). Raises NotFound, Conflict
    (not_a_desk_event, late_reason_window), InvalidInput (reason_required, unknown_reason, note_too_long)."""
    event = await session.get(TriageEvent, event_id, populate_existing=True)
    if event is None:
        raise NotFound("unknown_event")
    if event.source != "desk":
        raise Conflict("not_a_desk_event")
    if (now or datetime.now(UTC)) - event.created_at > timedelta(minutes=DESK_LATE_REASON_MINUTES):
        raise Conflict("late_reason_window")
    new_reason = None if reason is UNSET or not reason else reason
    if (event.pile == "not_relevant" and reason is not UNSET and new_reason is None) or (
        new_reason is None and note is None
    ):
        raise InvalidInput("reason_required", allowed=list(REASONS[event.pile]))
    check_reason(event.pile, new_reason or event.reason, note)
    if new_reason is not None:
        event.reason = new_reason
    if note is not None:
        event.note = note
    await session.commit()
    return event


async def history(session: AsyncSession, paper_id: uuid.UUID) -> list[TriageEvent]:
    """A paper's events, newest first. Raises NotFound, Gone."""
    await papers.get_paper(session, paper_id)
    rows = await session.scalars(
        select(TriageEvent)
        .where(TriageEvent.paper_id == paper_id)
        .order_by(TriageEvent.created_at.desc(), TriageEvent.id.desc())
    )
    return list(rows)


async def summary(session: AsyncSession, session_id: uuid.UUID) -> dict:
    """What a desk session decided, leaving out decisions a later undo took back. Unknown session: all zeros."""
    undone = select(TriageEvent.undone_event_id).where(TriageEvent.undone_event_id.is_not(None))
    rows = await session.execute(
        select(
            TriageEvent.pile,
            func.count(),
            func.coalesce(func.sum(TriageEvent.card_ms), 0),
            func.count().filter(TriageEvent.pdf_opened),
        )
        .where(TriageEvent.session_id == session_id, TriageEvent.source == "desk", TriageEvent.id.not_in(undone))
        .group_by(TriageEvent.pile)
    )
    per_pile: dict[str, int] = {}
    skipped = card_ms = pdf_opened = 0
    for pile, n, ms, pdf in rows:
        if pile == "skip":
            skipped = n
        else:
            per_pile[pile] = n
        card_ms += int(ms)
        pdf_opened += pdf
    return {
        "per_pile": per_pile,
        "skipped": skipped,
        "card_ms": card_ms,
        "pdf_opened": pdf_opened,
        "decided": sum(per_pile.values()),
    }
