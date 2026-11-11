import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from test_draft_review import Routed, issues
from test_manuscript_papers import setup

from app.core import draft_review, manuscripts, queue
from app.core import manuscript_draft_review as mdr
from app.core.errors import Conflict, InvalidInput
from app.models import LLMConnection, LLMModel, Manuscript
from app.models import ManuscriptDraftReview as Row
from app.providers.base import LLMError, LLMUnavailable
from app.workers import manuscript_draft_review as worker
from app.workers import manuscript_section_review as section_worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
BODY = (
    "\\begin{document}\n\\section{Intro}\n"
    + " ".join(f"Sentence {i} claims that sleep improves memory." for i in range(12))
    + "\n\\end{document}\n"
)
CLAIMS = (
    "\\begin{document}\n\\section{Intro}\n"
    + " ".join(f"Claim number {i} says that method {i} beats baseline {i} on every single task." for i in range(30))
    + "\n\\end{document}\n"
)
ISSUE = {
    "severity": "major",
    "section": "Intro",
    "summary": "The memory claim has no figure behind it",
    "evidence_quote": "Sentence 3 claims that sleep improves memory",
    "close_criterion": "The claim must point to a number",
}


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    async def stream(self, system, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0) if self.replies else '{"refuted": false, "reason": "fair"}'
        if isinstance(reply, Exception):
            raise reply
        yield reply if isinstance(reply, str) else json.dumps(reply)  # ask_json joins strings


class Blocking:
    """Its first answer waits for a gate the test opens, so the test can cancel while the job is inside a call."""

    model = "fake:blocking"

    def __init__(self, gate):
        self.gate, self.prompts = gate, []

    async def stream(self, system, prompt):
        self.prompts.append(prompt)
        await self.gate.wait()
        yield json.dumps({"issues": []})


@pytest.fixture(autouse=True)
def wiring(session, arq, monkeypatch, local_default_model):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)
    monkeypatch.setattr(section_worker, "SessionLocal", shared_session)  # the default-model check reads through it


async def doc(session, text=BODY, files=None):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    for path, body in (files or {"main.tex": text}).items():
        await manuscripts.upsert_text(session, m.id, path, body)
    return m


async def one(session, mid):
    return await session.scalar(select(Row).where(Row.manuscript_id == mid).execution_options(populate_existing=True))


async def rows(session, mid):
    return list(
        await session.scalars(select(Row).where(Row.manuscript_id == mid).execution_options(populate_existing=True))
    )


async def go(session, m, **kw):
    kw = {"mode": "light", "confirm_remote": False, "confirm_full": False} | kw
    return await mdr.start(session, m.id, **kw)


async def test_start_stores_paper_and_files_queues_the_job(session, arq):
    m = await doc(session)
    out = await go(session, m)
    assert (out["status"], out["mode"], out["calls_max"], out["ai"]) == ("queued", "light", 11, True)
    row = await one(session, m.id)
    assert "Sentence 3" in row.source
    assert isinstance(row.inputs["files"], list) and row.inputs["files"][0][0] == "main.tex"
    assert arq.jobs == [("review_manuscript_draft", str(row.id))]


async def test_file_order_survives_the_database(session, arq):
    z = "\\section{Results}\n" + " ".join(
        f"Result {i} shows that the cache halves latency on task {i}." for i in range(6)
    )
    a = "\\section{Intro}\n" + " ".join(
        f"Intro {i} claims that the cache halves latency for everyone." for i in range(6)
    )
    main = "\\begin{document}\n\\input{sections/z}\n\\input{sections/a}\n\\end{document}\n"
    m = await doc(session, files={"main.tex": main, "sections/z.tex": z, "sections/a.tex": a})
    await go(session, m)
    row = await one(session, m.id)  # read back from PostgreSQL, not from the session's copy
    assert [p for p, _ in row.inputs["files"]] == ["main.tex", "sections/z.tex", "sections/a.tex"]
    in_a = {**ISSUE, "evidence_quote": "Intro 2 claims that the cache halves latency for everyone"}
    in_z = {**ISSUE, "evidence_quote": "Result 1 shows that the cache halves latency on task 1"}
    llm = Scripted({"issues": [in_a]}, {"issues": [in_z]}, {"issues": []})
    await worker.review_manuscript_draft({"llm": llm}, str(row.id))
    got = await one(session, m.id)
    assert [(i["id"], i["file"]) for i in got.issues] == [("I-01", "sections/z.tex"), ("I-02", "sections/a.tex")]
    state = (await mdr.state(session, m.id))["review"]
    assert [i["file"] for i in state["issues"]] == ["sections/z.tex", "sections/a.tex"]


@pytest.mark.parametrize(
    "body, reason",
    [
        ("\\begin{document}\nToo short.\n\\end{document}", "paper_too_short"),
        ("\\begin{document}\n" + "word " * 9000 + "\n\\end{document}", "paper_too_long"),
    ],
)
async def test_start_refuses_a_paper_too_short_or_long(session, body, reason):
    m = await doc(session, body)
    with pytest.raises(InvalidInput, match=reason):
        await go(session, m)
    assert await rows(session, m.id) == []


async def test_start_refuses_a_missing_main_file_and_a_running_review(session):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await session.execute(update(Manuscript).where(Manuscript.id == m.id).values(main_file="missing.tex"))
    with pytest.raises(InvalidInput, match="not_tex"):
        await go(session, m)
    m = await doc(session)
    await go(session, m)
    with pytest.raises(Conflict, match="review_running"):
        await go(session, m)


async def test_start_refuses_an_unconfirmed_remote_model_and_no_model(session):
    m = await doc(session)
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await go(session, m)
    await session.execute(update(LLMModel).values(is_default=False))
    with pytest.raises(Conflict, match="no_model"):
        await go(session, m)


async def test_a_second_start_replaces_the_first_once_the_first_is_finished_or_dead(session):
    m = await doc(session)
    first = await go(session, m)
    await session.execute(update(Row).where(Row.id == first["id"]).values(status="done"))
    await go(session, m)
    assert len(await rows(session, m.id)) == 1
    (row,) = await rows(session, m.id)
    await session.execute(
        update(Row)
        .where(Row.id == row.id)
        .values(status="running", updated_at=datetime.now(UTC) - timedelta(minutes=21))
    )
    out = await go(session, m)
    assert out["status"] == "queued" and len(await rows(session, m.id)) == 1


async def test_queue_failure_marks_the_row_failed(session, monkeypatch):
    async def down(*a, **k):
        raise ConnectionError("redis is gone")

    monkeypatch.setattr(queue, "enqueue", down)
    m = await doc(session)
    out = await go(session, m)
    assert (out["status"], out["reason"]) == ("failed", "queue_unavailable")


async def test_estimate_gives_both_modes_and_makes_no_model_call(session, arq):
    m = await doc(session)
    est = await mdr.estimate(session, m.id)
    assert est["too_long"] is False and est["paper_chars"] >= 200
    assert est["modes"] == draft_review.estimates(est["paper_chars"])
    light, full = est["modes"]
    assert (light["likely_calls"], light["max_calls"]) == (11, 11)
    assert (full["likely_calls"], full["max_calls"]) == (42, 54)
    assert full["approx_input_tokens"] > light["approx_input_tokens"]
    assert arq.jobs == [] and await rows(session, m.id) == []
    big = await doc(session, "\\begin{document}\n" + "word " * 9000 + "\n\\end{document}\n")
    assert (await mdr.estimate(session, big.id))["too_long"] is True


async def test_full_needs_an_explicit_confirm(session):
    m = await doc(session)
    with pytest.raises(Conflict, match="full_needs_confirm") as caught:
        await go(session, m, mode="full", confirm_full=False)
    assert (caught.value.details["likely_calls"], caught.value.details["max_calls"]) == (42, 54)
    assert await rows(session, m.id) == []
    out = await go(session, m, mode="full", confirm_full=True)
    assert (out["mode"], out["calls_max"]) == ("full", 54)
    light = await doc(session, BODY)  # a light start with confirm_full set is harmless
    assert (await go(session, light, confirm_full=True))["mode"] == "light"


async def test_full_remote_check_comes_first(session):
    m = await doc(session)
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await go(session, m, mode="full", confirm_full=True)


async def test_worker_runs_the_rows_mode(session):
    m = await doc(session, CLAIMS)
    await go(session, m, mode="light")
    light = Routed(issues(0, 1))
    await worker.review_manuscript_draft({"llm": light}, str((await one(session, m.id)).id))
    assert len(light.calls) == 4  # three reviewers and one skeptic
    await session.execute(update(Row).where(Row.manuscript_id == m.id).values(status="done"))
    await go(session, m, mode="full", confirm_full=True)
    full = Routed(issues(0, 1))
    await worker.review_manuscript_draft({"llm": full}, str((await one(session, m.id)).id))
    assert len(full.calls) == 9 and (await one(session, m.id)).counts["rounds_run"] == 2  # round 2 is dry


async def test_cancel_marks_failed_cancelled_and_the_running_job_stops(session):
    m = await doc(session)
    out = await go(session, m)
    gate = asyncio.Event()
    llm = Blocking(gate)
    task = asyncio.create_task(worker.review_manuscript_draft({"llm": llm}, str(out["id"])))
    while not llm.prompts:
        await asyncio.sleep(0)
    cancelled = await mdr.cancel(session, m.id, out["id"])
    gate.set()
    await task
    (row,) = await rows(session, m.id)
    assert (cancelled["status"], cancelled["reason"]) == ("failed", "cancelled")
    assert (row.status, row.reason) == ("failed", "cancelled") and len(llm.prompts) == 1


async def test_worker_done_writes_issues_counts_and_model(session):
    m = await doc(session)
    out = await go(session, m)
    llm = Scripted({"issues": [ISSUE]}, {"issues": []}, {"issues": []})
    await worker.review_manuscript_draft({"llm": llm}, str(out["id"]))
    row = await one(session, m.id)
    assert (row.status, row.model, row.stage, row.calls_done) == ("done", "fake:scripted", None, 4)
    assert (row.issues[0]["id"], row.issues[0]["file"]) == ("I-01", "main.tex")
    assert row.counts["rounds_run"] == 1


async def test_worker_failure_reasons(session):
    for replies, reason in [
        ([LLMUnavailable("down")], "model_unavailable"),
        # a bad reply is not retried, so one bad reply per reviewer is enough to fail all three
        (["nothing", "nothing", "nothing"], "model_error"),
        ([LLMError("boom")] * 3, "model_error"),
        ([RuntimeError("bug")], "check_failed"),
    ]:
        m = await doc(session)
        out = await go(session, m)
        await worker.review_manuscript_draft({"llm": Scripted(*replies)}, str(out["id"]))
        (row,) = await rows(session, m.id)
        assert (row.status, row.reason) == ("failed", reason)
        await session.execute(update(Row).where(Row.manuscript_id == m.id).values(status="done"))


async def test_worker_refuses_a_remote_default_that_appeared_after_start(session):
    m = await doc(session)
    out = await go(session, m)
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    await worker.review_manuscript_draft({}, str(out["id"]))
    (row,) = await rows(session, m.id)
    assert (row.status, row.reason, row.confirm_remote) == ("failed", "remote_model_needs_confirm", False)


async def test_a_row_the_job_did_not_take_is_left_alone(session):
    m = await doc(session)
    out = await go(session, m)
    await session.execute(update(Row).where(Row.id == out["id"]).values(status="done"))
    llm = Scripted()
    await worker.review_manuscript_draft({"llm": llm}, str(out["id"]))
    assert llm.prompts == [] and (await one(session, m.id)).status == "done"
