from contextlib import asynccontextmanager

import pytest

from app.core.screening_suggest import SYSTEM_PROMPT
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import FakeLLM
from app.workers import screening_suggest as worker_module
from tests.screening_pool import make_pool

pytestmark = pytest.mark.anyio

POSITIVE = "randomised controlled trial of sleep deprivation in adults"
NEGATIVE = "a survey of graph neural networks for molecules"


class ScriptedLLM(FakeLLM):
    """Answers each call from `replies` in order; an Exception instance is raised instead."""

    def __init__(self, replies, on_call=None):
        super().__init__(model="scripted")
        self.replies = list(replies)
        self.on_call = on_call

    async def stream(self, system, prompt):
        self.calls.append((system, prompt))
        if self.on_call:
            await self.on_call(len(self.calls))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield reply


@pytest.fixture
def worker(session, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(worker_module, "SessionLocal", shared_session)

    def use(llm):
        monkeypatch.setattr(worker_module, "build_llm", lambda connection, name, transport=None: llm)
        return llm

    return use


async def _running(session, rows, criteria="RCTs on sleep in adults"):
    workspace, hits = await make_pool(session, rows)
    workspace.screening_criteria, workspace.suggest_status = criteria, "running"
    await session.flush()
    return workspace, hits


async def test_worker_suggests_in_ranked_order_and_never_sets_status(session, worker):
    workspace, hits = await _running(session, [
        (POSITIVE, "relevant"), (NEGATIVE, "not_relevant"),
        ("graph neural network benchmark for molecules", None), ("sleep deprivation trial in older adults", None),
    ])
    llm = worker(ScriptedLLM(["INCLUDE\nFits.", "EXCLUDE wrong_topic\nGraphs."]))
    await worker_module.suggest_screening({}, str(workspace.id))
    assert "sleep deprivation trial in older adults" in llm.calls[0][1]  # ranked first
    assert all(system == SYSTEM_PROMPT for system, _ in llm.calls)
    for hit in hits:
        await session.refresh(hit)
    assert (hits[3].suggestion, hits[2].suggestion, hits[2].suggestion_reason) == ("include", "exclude", "wrong_topic")
    assert (hits[2].stage1_status, hits[3].stage1_status) == (None, None)
    assert hits[3].suggestion_model is not None and hits[3].suggested_at is not None
    await session.refresh(workspace)
    assert (workspace.suggest_status, workspace.suggest_done) == ("idle", 2)


async def test_worker_skips_hit_decided_mid_job_and_never_sets_status(session, worker):
    workspace, hits = await _running(session, [("a", None), ("b", None)])

    async def decide_second(call):
        if call == 1:
            hits[1].stage1_status = "maybe"
            await session.flush()

    llm = worker(ScriptedLLM(["INCLUDE\nx"], on_call=decide_second))
    await worker_module.suggest_screening({}, str(workspace.id))
    assert len(llm.calls) == 1
    await session.refresh(hits[1])
    assert (hits[1].suggestion, hits[1].stage1_status) == (None, "maybe")


async def test_worker_skips_hit_with_no_text(session, worker):
    workspace, hits = await _running(session, [("", None), ("sleep", None)])
    hits[0].external_ref_id = None
    hits[0].normalized_title = ""
    await session.flush()
    llm = worker(ScriptedLLM(["INCLUDE\nx"]))
    await worker_module.suggest_screening({}, str(workspace.id))
    assert len(llm.calls) == 1
    await session.refresh(hits[0])
    assert hits[0].suggestion is None


async def test_stop_mid_job_ends_after_the_current_hit(session, worker):
    workspace, hits = await _running(session, [("a", None), ("b", None), ("c", None)])

    async def stop_after_first(call):
        if call == 1:
            workspace.suggest_status = "stopping"
            await session.flush()

    llm = worker(ScriptedLLM(["INCLUDE\nx", "INCLUDE\nx", "INCLUDE\nx"], on_call=stop_after_first))
    await worker_module.suggest_screening({}, str(workspace.id))
    assert len(llm.calls) == 1
    await session.refresh(workspace)
    assert (workspace.suggest_status, workspace.suggest_done) == ("idle", 1)


async def test_a_model_error_on_one_hit_is_unsure_and_the_job_goes_on(session, worker):
    workspace, hits = await _running(session, [("a", None), ("b", None)])
    worker(ScriptedLLM([LLMError("boom"), "INCLUDE\nx"]))
    await worker_module.suggest_screening({}, str(workspace.id))
    await session.refresh(hits[0])
    await session.refresh(hits[1])
    assert (hits[0].suggestion, hits[0].suggestion_note) == ("unsure", "model error")
    assert hits[1].suggestion == "include"


async def test_an_unreachable_model_ends_the_job_with_its_message(session, worker):
    workspace, hits = await _running(session, [("a", None), ("b", None)])
    worker(ScriptedLLM([LLMUnavailable("Can't reach localhost:11434")]))
    await worker_module.suggest_screening({}, str(workspace.id))
    await session.refresh(workspace)
    assert (workspace.suggest_status, workspace.suggest_error) == ("idle", "Can't reach localhost:11434")
    for hit in hits:
        await session.refresh(hit)
        assert hit.suggestion is None


async def test_resume_only_asks_about_hits_without_a_suggestion(session, worker):
    workspace, hits = await _running(session, [("a", None), ("b", None)])
    hits[0].suggestion = "include"
    await session.flush()
    llm = worker(ScriptedLLM(["UNSURE\nx"]))
    await worker_module.suggest_screening({}, str(workspace.id))
    assert len(llm.calls) == 1


async def test_the_advisory_lock_is_released_even_when_the_final_status_commit_fails(session, worker, monkeypatch):
    """A live-check run on 2026-10-03 found a stuck job: suggest_status froze at "stopping" and the advisory lock
    stayed held forever, blocking every future suggestion run on that workspace until someone manually restarted
    the worker and reset the row. Root cause: `finally`'s `workspace.suggest_status = "idle"; await
    session.commit()` and the `_UNLOCK` call right after it were not independently guaranteed — if the commit
    raised or was cancelled (the live run's own `async with SessionLocal()` connection is pooled and reused, so a
    lock left unreleased here leaks into whatever request borrows that connection next), `_UNLOCK` was never
    reached at all."""
    workspace, hits = await _running(session, [("a", None)])
    worker(ScriptedLLM(["INCLUDE\nx"]))

    real_commit = session.commit
    commit_calls = {"n": 0}

    async def flaky_commit():
        commit_calls["n"] += 1
        if commit_calls["n"] == 2:  # the loop's own per-hit commit is call 1; finally's status="idle" commit is 2
            raise RuntimeError("simulated commit failure")
        await real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)

    real_execute = session.execute
    executed_unlock = {"called": False}

    async def spy_execute(stmt, *args, **kwargs):
        if stmt is worker_module._UNLOCK:
            executed_unlock["called"] = True
        return await real_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(session, "execute", spy_execute)

    with pytest.raises(RuntimeError, match="simulated commit failure"):
        await worker_module.suggest_screening({}, str(workspace.id))

    assert executed_unlock["called"] is True


async def test_a_job_for_an_idle_workspace_does_nothing(session, worker):
    workspace, _ = await make_pool(session, [("a", None)])
    llm = worker(ScriptedLLM([]))
    await worker_module.suggest_screening({}, str(workspace.id))
    assert llm.calls == []
