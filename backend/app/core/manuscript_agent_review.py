"""Start a whole-manuscript citation review and read it, for an outside agent (the MCP)."""

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import manuscript_review as review
from app.core import manuscript_review_all as review_all
from app.core import manuscript_review_report as report
from app.core.errors import NotFound, error_code
from app.schemas.manuscript_review import ReportItemOut, ReviewRunOut

MAX_ITEMS = 200


class ReviewStarted(BaseModel):
    started: bool
    needs_confirm: bool
    pairs: int
    files: int
    run: ReviewRunOut | None


class ReviewView(BaseModel):
    run: ReviewRunOut | None
    counts: dict[str, int]
    dismissed: int
    items: list[ReportItemOut]
    truncated: int  # items beyond the cap


async def start_review(
    session: AsyncSession, mid: uuid.UUID, include_uncited: bool, confirm_large: bool, allow_remote: bool
) -> ReviewStarted:
    est = await review_all.estimate(session, mid, include_uncited=include_uncited)
    if est["pairs"] > est["max_pairs"]:  # too big to confirm: start_all refuses with too_many_claims
        await review_all.start_all(
            session, mid, include_uncited=include_uncited, confirm_large=True, confirm_remote=allow_remote
        )
    if est["needs_confirm"] and not confirm_large:  # show the owner the count first; nothing is written
        return ReviewStarted(started=False, needs_confirm=True, pairs=est["pairs"], files=len(est["files"]), run=None)
    run = await review_all.start_all(
        session, mid, include_uncited=include_uncited, confirm_large=confirm_large, confirm_remote=allow_remote
    )
    return ReviewStarted(
        started=True, needs_confirm=False, pairs=est["pairs"], files=len(est["files"]), run=ReviewRunOut(**run)
    )


async def get_review(session: AsyncSession, mid: uuid.UUID) -> ReviewView:
    try:
        rep = await report.build(session, mid)
    except NotFound as exc:
        if error_code(exc) != "unknown_run":  # an unknown manuscript is still an error
            raise
        return ReviewView(run=None, counts={}, dismissed=0, items=[], truncated=0)
    items = [i for f in rep["files"] for i in f["items"] if i["outcome"] != "not_claim"]
    # ponytail: file name order, not run order, among equals
    items.sort(key=lambda i: (i["outcome"] not in report.ATTENTION, i["file"], i["ord"]))
    return ReviewView(
        run=ReviewRunOut(**rep["run"]),
        counts=rep["counts"],
        dismissed=rep["dismissed"],
        items=[ReportItemOut(**i) for i in items[:MAX_ITEMS]],
        truncated=max(0, len(items) - MAX_ITEMS),
    )


async def cancel_review(session: AsyncSession, mid: uuid.UUID, run_id: uuid.UUID) -> ReviewRunOut:
    return ReviewRunOut(**await review.cancel(session, mid, run_id))
