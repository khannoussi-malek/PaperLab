import asyncio
import uuid

from fastapi import APIRouter, Query, Response

from app.api.deps import SessionDep
from app.core import manuscript_review as review
from app.core import manuscript_review_all as review_all
from app.core import manuscript_review_report as review_report
from app.core import manuscripts
from app.schemas.manuscript_review import (
    EstimateOut,
    LocateIn,
    LocateOut,
    ReportOut,
    ReviewAllIn,
    ReviewIn,
    ReviewOut,
    ReviewRunOut,
)

router = APIRouter(tags=["manuscripts"])
BASE = "/api/manuscripts/{manuscript_id}/review"


@router.post(BASE, status_code=202)
async def start_review(manuscript_id: uuid.UUID, body: ReviewIn, session: SessionDep) -> ReviewRunOut:
    selection = (body.from_, body.to if body.to is not None else body.from_) if body.from_ is not None else None
    return ReviewRunOut(
        **await review.start(
            session,
            manuscript_id,
            file=body.file,
            base=body.base,
            selection=selection,
            include_uncited=body.include_uncited,
            confirm_remote=body.confirm_remote,
        )
    )


@router.get(BASE)
async def review_state(manuscript_id: uuid.UUID, session: SessionDep, file: str = Query()) -> ReviewOut:
    return ReviewOut(**await review.state(session, manuscript_id, file))


@router.post(BASE + "/locate")
async def locate(manuscript_id: uuid.UUID, body: LocateIn, session: SessionDep) -> LocateOut:
    await manuscripts.get(session, manuscript_id)
    return LocateOut(sentences=await asyncio.to_thread(review.locate, body.text))


@router.get(BASE + "/all/estimate")
async def estimate_review_all(
    manuscript_id: uuid.UUID, session: SessionDep, include_uncited: bool = True
) -> EstimateOut:
    return EstimateOut(**await review_all.estimate(session, manuscript_id, include_uncited=include_uncited))


@router.post(BASE + "/all", status_code=202)
async def start_review_all(manuscript_id: uuid.UUID, body: ReviewAllIn, session: SessionDep) -> ReviewRunOut:
    return ReviewRunOut(**await review_all.start_all(session, manuscript_id, **body.model_dump()))


@router.get(BASE + "/report")
async def review_report_json(manuscript_id: uuid.UUID, session: SessionDep) -> ReportOut:
    return ReportOut(**await review_report.build(session, manuscript_id))


@router.get(BASE + "/report.md")
async def review_report_markdown(manuscript_id: uuid.UUID, session: SessionDep) -> Response:
    body = review_report.render_markdown(await review_report.build(session, manuscript_id))
    return Response(
        body,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="citation-review.md"'},
    )


@router.post(BASE + "/{run_id}/cancel")
async def cancel_review(manuscript_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep) -> ReviewRunOut:
    return ReviewRunOut(**await review.cancel(session, manuscript_id, run_id))


@router.put(BASE + "/dismissals/{sentence_hash}", status_code=204)
async def dismiss_claim(manuscript_id: uuid.UUID, sentence_hash: str, session: SessionDep) -> Response:
    await review.dismiss(session, manuscript_id, sentence_hash)
    return Response(status_code=204)


@router.delete(BASE + "/dismissals/{sentence_hash}", status_code=204)
async def restore_claim(manuscript_id: uuid.UUID, sentence_hash: str, session: SessionDep) -> Response:
    await review.restore(session, manuscript_id, sentence_hash)
    return Response(status_code=204)
