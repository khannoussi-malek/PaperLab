import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core import manuscript_draft_review as review
from app.schemas.manuscript_draft_review import (
    DraftReviewEstimate,
    DraftReviewIn,
    DraftReviewOut,
    DraftReviewState,
)

router = APIRouter(tags=["manuscripts"])
BASE = "/api/manuscripts/{manuscript_id}/draft-review"


@router.post(BASE, status_code=202)
async def start_draft_review(manuscript_id: uuid.UUID, body: DraftReviewIn, session: SessionDep) -> DraftReviewOut:
    return DraftReviewOut(**await review.start(session, manuscript_id, **body.model_dump()))


@router.get(BASE)
async def draft_review(manuscript_id: uuid.UUID, session: SessionDep) -> DraftReviewState:
    return DraftReviewState(**await review.state(session, manuscript_id))


@router.get(BASE + "/estimate")
async def draft_review_estimate(manuscript_id: uuid.UUID, session: SessionDep) -> DraftReviewEstimate:
    return DraftReviewEstimate(**await review.estimate(session, manuscript_id))


@router.post(BASE + "/{review_id}/cancel")
async def cancel_draft_review(manuscript_id: uuid.UUID, review_id: uuid.UUID, session: SessionDep) -> DraftReviewOut:
    return DraftReviewOut(**await review.cancel(session, manuscript_id, review_id))
