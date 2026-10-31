import asyncio
import uuid

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.core import manuscript_section_review as review
from app.core import manuscripts
from app.schemas.manuscript_section_review import (
    SectionLocateIn,
    SectionLocateOut,
    SectionReviewIn,
    SectionReviewOut,
    SectionReviewsOut,
)

router = APIRouter(tags=["manuscripts"])
BASE = "/api/manuscripts/{manuscript_id}/section-review"


@router.post(BASE, status_code=202)
async def start_section_review(
    manuscript_id: uuid.UUID, body: SectionReviewIn, session: SessionDep
) -> SectionReviewOut:
    return SectionReviewOut(**await review.start(session, manuscript_id, **body.model_dump()))


@router.get(BASE)
async def section_reviews(manuscript_id: uuid.UUID, session: SessionDep, file: str = Query()) -> SectionReviewsOut:
    return SectionReviewsOut(**await review.state(session, manuscript_id, file))


@router.post(BASE + "/locate")
async def locate_sections(manuscript_id: uuid.UUID, body: SectionLocateIn, session: SessionDep) -> SectionLocateOut:
    manuscript = await manuscripts.get(session, manuscript_id)
    sections = await asyncio.to_thread(review.locate, body.file, body.text, manuscript.main_file)
    return SectionLocateOut(sections=sections)


@router.post(BASE + "/{review_id}/cancel")
async def cancel_section_review(
    manuscript_id: uuid.UUID, review_id: uuid.UUID, session: SessionDep
) -> SectionReviewOut:
    return SectionReviewOut(**await review.cancel(session, manuscript_id, review_id))
