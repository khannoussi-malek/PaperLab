"""The triage desk's decisions (D119): a pile moves a paper's `triage` / `reading_pass` and appends one event."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import papers
from app.core.errors import InvalidInput
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
