import uuid

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.core import triage
from app.schemas.triage import (
    TriageDecisionIn,
    TriageDecisionOut,
    TriageEventOut,
    TriageHistoryOut,
    TriageReasonIn,
    TriageSummaryOut,
)

router = APIRouter(prefix="/api", tags=["triage"])


@router.post("/papers/{paper_id}/triage-decisions", status_code=201, response_model=TriageDecisionOut)
async def decide(paper_id: uuid.UUID, payload: TriageDecisionIn, session: SessionDep, response: Response):
    """A desk decision. 201; 200 with the first result when `client_id` was already used (a retry). 404 unknown
    paper, 410 merged, 422 reason_required | unknown_reason (with allowed) | note_too_long."""
    paper, event, replayed = await triage.decide(session, paper_id, **payload.model_dump())
    if replayed:
        response.status_code = 200
    return {"paper": paper, "event": event}


@router.get("/papers/{paper_id}/triage-events")
async def paper_history(paper_id: uuid.UUID, session: SessionDep) -> TriageHistoryOut:
    return TriageHistoryOut(events=[TriageEventOut.model_validate(e) for e in await triage.history(session, paper_id)])


@router.patch("/triage-events/{event_id}")
async def add_reason(event_id: uuid.UUID, payload: TriageReasonIn, session: SessionDep) -> TriageEventOut:
    """Add a reason and/or note to a desk decision made in the last few minutes. A field not sent stays as it was."""
    sent = payload.model_fields_set
    event = await triage.add_reason(
        session,
        event_id,
        reason=payload.reason if "reason" in sent else triage.UNSET,
        note=payload.note if "note" in sent else None,
    )
    return TriageEventOut.model_validate(event)


@router.post("/triage-events/{event_id}/undo")
async def undo(event_id: uuid.UUID, session: SessionDep) -> TriageDecisionOut:
    """409 changed_since | already_undone | not_a_desk_event."""
    paper, event = await triage.undo(session, event_id)
    return TriageDecisionOut(paper=paper, event=event)


@router.get("/triage-summary")
async def summary(session_id: uuid.UUID, session: SessionDep) -> TriageSummaryOut:
    return TriageSummaryOut(**await triage.summary(session, session_id))
