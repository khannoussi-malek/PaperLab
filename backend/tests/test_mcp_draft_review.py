"""The whole-draft review tools through an in-process client, on the test's rolled-back session."""

import uuid

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from sqlalchemy import update
from test_manuscript_papers import setup
from test_remote_confirm import _remote

from app.core import manuscript_draft_review, manuscripts
from app.core.errors import DomainError, error_code
from app.models import ManuscriptDraftReview as Row

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


@pytest.fixture(autouse=True)
def default_model(local_default_model):
    return local_default_model
BODY = (
    "\\begin{document}\n\\section{Intro}\n"
    + " ".join(f"Sentence {i} claims that sleep improves memory." for i in range(12))
    + "\n\\end{document}\n"
)


def failed(response, code):
    assert response.is_error
    assert response.structured_content["error"] == code, response.structured_content
    return response.structured_content


async def manuscript(session, text=BODY):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", text)
    return m


async def test_start_then_get_the_review(session, jobs):
    m = await manuscript(session)
    assert result(await call("get_draft_review", manuscript_id=str(m.id))) == {"review": None}
    out = result(await call("start_draft_review", manuscript_id=str(m.id)))
    assert out["status"] == "queued" and out["mode"] == "light"
    assert [job[0] for job in jobs.jobs] == ["review_manuscript_draft"]
    got = result(await call("get_draft_review", manuscript_id=str(m.id)))
    assert got["review"]["id"] == out["id"] and got["review"]["status"] == "queued"


async def test_a_short_paper_is_an_error_the_model_can_read(session):
    m = await manuscript(session, "\\begin{document}\nToo short.\n\\end{document}\n")
    error = failed(await call("start_draft_review", manuscript_id=str(m.id)), "paper_too_short")
    assert "detail" in error


async def test_full_needs_a_confirm_and_then_queues_a_full_review(session, jobs):
    m = await manuscript(session)
    error = failed(await call("start_draft_review", manuscript_id=str(m.id), mode="full"), "full_needs_confirm")
    assert (error["likely_calls"], error["max_calls"]) == (42, 54)
    assert jobs.jobs == []
    out = result(await call("start_draft_review", manuscript_id=str(m.id), mode="full", confirm_full=True))
    assert (out["mode"], out["calls_max"]) == ("full", 54)


async def test_a_remote_default_needs_confirm_remote(session, jobs):
    m = await manuscript(session)
    await _remote(session)
    failed(await call("start_draft_review", manuscript_id=str(m.id)), "remote_model_needs_confirm")
    out = result(await call("start_draft_review", manuscript_id=str(m.id), confirm_remote=True))
    assert out["status"] == "queued"


async def test_an_unknown_manuscript_gives_the_same_error_as_check_manuscript(session):
    missing = str(uuid.uuid4())
    checked = await call("check_manuscript", manuscript_id=missing)
    started = await call("start_draft_review", manuscript_id=missing)
    assert checked.is_error and started.is_error
    assert started.structured_content["error"] == checked.structured_content["error"]


async def test_cancel_a_running_review_stops_it(session, jobs):
    m = await manuscript(session)
    out = result(await call("start_draft_review", manuscript_id=str(m.id)))
    await session.execute(update(Row).where(Row.id == uuid.UUID(out["id"])).values(status="running"))
    await session.flush()
    cancelled = result(await call("cancel_draft_review", manuscript_id=str(m.id), review_id=out["id"]))
    assert (cancelled["status"], cancelled["reason"]) == ("failed", "cancelled")
    got = result(await call("get_draft_review", manuscript_id=str(m.id)))
    assert (got["review"]["status"], got["review"]["reason"]) == ("failed", "cancelled")


async def test_cancel_a_finished_review_returns_it_unchanged(session, jobs):
    m = await manuscript(session)
    out = result(await call("start_draft_review", manuscript_id=str(m.id)))
    await session.execute(update(Row).where(Row.id == uuid.UUID(out["id"])).values(status="done", reason=None))
    await session.flush()
    again = result(await call("cancel_draft_review", manuscript_id=str(m.id), review_id=out["id"]))
    assert (again["status"], again["reason"]) == ("done", None)


async def test_an_unknown_review_gives_the_core_error_code(session, jobs):
    m = await manuscript(session)
    with pytest.raises(DomainError) as core:
        await manuscript_draft_review.cancel(session, m.id, uuid.uuid4())
    missing = str(uuid.uuid4())
    failed(await call("cancel_draft_review", manuscript_id=str(m.id), review_id=missing), error_code(core.value))
