import uuid

from fastapi import APIRouter, Query, Response

from app.api.deps import SessionDep
from app.core import manuscript_review as review
from app.core import manuscripts
from app.schemas.manuscript_review import LocateIn, LocateOut, ReviewIn, ReviewOut, ReviewRunOut

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
        )
    )


@router.get(BASE)
async def review_state(manuscript_id: uuid.UUID, session: SessionDep, file: str = Query()) -> ReviewOut:
    return ReviewOut(**await review.state(session, manuscript_id, file))


@router.post(BASE + "/locate")
async def locate(manuscript_id: uuid.UUID, body: LocateIn, session: SessionDep) -> LocateOut:
    await manuscripts.get(session, manuscript_id)
    return LocateOut(sentences=review.locate(body.text))


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
