"""The whole-manuscript review through the MCP tools: start, read and cancel, on the test's rolled-back session."""

import uuid
from contextlib import asynccontextmanager

import pytest
from mcp import Client
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from sqlalchemy import select, update
from test_manuscript_papers import setup

from app.core import manuscript_papers, manuscripts
from app.core import manuscript_review_report as report
from app.models import ManuscriptClaimCheck, ManuscriptFile, ManuscriptReviewRun
from app.workers import manuscript_review as worker
from mcp_server import server

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


@pytest.fixture(autouse=True)
def default_model(local_default_model):
    """A local default model, so a start never reads the dev database's settings."""
    return local_default_model


def failed(response, code):
    assert response.is_error
    assert response.structured_content["error"] == code, response.structured_content
    return response.structured_content


async def bare(session, text_fn):
    """A manuscript whose only .tex file is main.tex; returns its id and the first paper's key."""
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    key = (await manuscript_papers.list_papers(session, m.id))[0]["key"]
    await session.execute(
        ManuscriptFile.__table__.delete().where(
            ManuscriptFile.manuscript_id == m.id, ManuscriptFile.path.like("sections/%")
        )
    )
    await manuscripts.upsert_text(session, m.id, "main.tex", text_fn(key))
    await session.flush()
    return str(m.id), key


def cites(n, key):
    return " ".join(f"Claim number {i} is well established \\cite{{{key}}}." for i in range(n))


async def test_a_small_review_starts_and_queues_one_job(session, jobs):
    mid, key = await bare(
        session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}. Walking is good for health."
    )
    out = result(await call("start_manuscript_review", manuscript_id=mid))
    assert out["started"] is True and out["needs_confirm"] is False and out["pairs"] == 1
    assert out["run"]["status"] == "queued" and out["run"]["file"] == "*"
    assert jobs.jobs == [("check_manuscript_citations", out["run"]["id"])]


async def test_more_than_30_pairs_need_confirm_large_and_write_nothing(session, jobs):
    mid, key = await bare(session, lambda k: cites(31, k))
    out = result(await call("start_manuscript_review", manuscript_id=mid))
    assert (out["started"], out["needs_confirm"], out["pairs"], out["files"], out["run"]) == (False, True, 31, 1, None)
    assert jobs.jobs == []
    assert (
        await session.scalars(select(ManuscriptClaimCheck).where(ManuscriptClaimCheck.manuscript_id == uuid.UUID(mid)))
    ).all() == []
    again = result(await call("start_manuscript_review", manuscript_id=mid, confirm_large=True))
    assert again["started"] is True and len(jobs.jobs) == 1


async def test_a_remote_default_model_is_refused_until_allow_remote(session, jobs):
    from app.models import LLMConnection, LLMModel

    mid, key = await bare(session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}.")
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    failed(await call("start_manuscript_review", manuscript_id=mid), "remote_model_needs_confirm")
    assert jobs.jobs == []
    assert result(await call("start_manuscript_review", manuscript_id=mid, allow_remote=True))["started"] is True


async def test_no_run_reads_as_empty(session):
    mid, key = await bare(session, lambda k: "Plain words are written here.")
    out = result(await call("get_manuscript_review", manuscript_id=mid))
    assert (out["run"], out["counts"], out["items"], out["truncated"]) == (None, {}, [], 0)


async def test_items_list_problems_first_and_cap_at_200(session, jobs):
    mid, key = await bare(
        session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}. Walking is good for health."
    )
    run = result(await call("start_manuscript_review", manuscript_id=mid, include_uncited=True))["run"]
    extra = [
        ManuscriptClaimCheck(
            manuscript_id=uuid.UUID(mid),
            run_id=uuid.UUID(run["id"]),
            file_path="main.tex",
            sentence_hash=uuid.uuid4().hex,
            sentence="Filler sentence here for the cap.",
            plain="Filler sentence here for the cap.",
            ord=100 + i,
            kind="uncited",
            status="done",
            verdict="supported" if i < 204 else "not_supported",
        )
        for i in range(205)
    ]
    session.add_all(extra)
    await session.flush()
    out = result(await call("get_manuscript_review", manuscript_id=mid))
    assert out["counts"] == {"supported": 204, "not_supported": 1, "unfinished": 2}
    assert len(out["items"]) == 200 and out["truncated"] == 7
    attention = [i["outcome"] in report.ATTENTION for i in out["items"]]
    assert attention[:3] == [True, True, True] and attention == sorted(attention, reverse=True)


async def test_more_than_600_pairs_is_too_many_claims_never_needs_confirm(session, jobs):
    mid, key = await bare(session, lambda k: cites(601, k))
    failed(await call("start_manuscript_review", manuscript_id=mid, confirm_large=True), "too_many_claims")
    assert jobs.jobs == []


async def test_cancel_a_queued_run_and_the_worker_leaves_its_rows_cancelled(session, jobs, monkeypatch):
    mid, key = await bare(session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}.")
    run_id = result(await call("start_manuscript_review", manuscript_id=mid, include_uncited=False))["run"]["id"]
    out = result(await call("cancel_manuscript_review_all", manuscript_id=mid, run_id=run_id))
    assert out["id"] == run_id

    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    await worker.check_manuscript_citations({}, run_id)
    row = (
        await session.scalars(select(ManuscriptClaimCheck).where(ManuscriptClaimCheck.manuscript_id == uuid.UUID(mid)))
    ).one()
    assert (row.status, row.reason) == ("failed", "cancelled")
    saved = await session.get(ManuscriptReviewRun, uuid.UUID(run_id), populate_existing=True)
    assert saved.status == "cancelled"


async def test_cancel_a_done_run_returns_it_unchanged(session, jobs):
    mid, key = await bare(session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}.")
    run_id = result(await call("start_manuscript_review", manuscript_id=mid, include_uncited=False))["run"]["id"]
    await session.execute(
        update(ManuscriptReviewRun).where(ManuscriptReviewRun.id == uuid.UUID(run_id)).values(status="done")
    )
    await session.flush()
    out = result(await call("cancel_manuscript_review_all", manuscript_id=mid, run_id=run_id))
    assert out["status"] == "done"


async def test_an_unknown_run_id_is_refused(session, jobs):
    mid, key = await bare(session, lambda k: "Plain words are written here.")
    failed(await call("cancel_manuscript_review_all", manuscript_id=mid, run_id=str(uuid.uuid4())), "unknown_run")


async def test_the_review_tools_are_listed_and_only_the_read_one_is_read_only():
    async with Client(server.mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in ("start_manuscript_review", "get_manuscript_review", "cancel_manuscript_review_all"):
        assert name in tools
    assert tools["get_manuscript_review"].annotations.read_only_hint is True
    assert (
        not tools["start_manuscript_review"].annotations
        or not tools["start_manuscript_review"].annotations.read_only_hint
    )
