"""M8.5 Ask each paper through POST /api/workspaces/{id}/chat with each_paper: true. The fake model (LLM_PROVIDER=fake)
finds every paper from its first passage."""

from contextlib import asynccontextmanager

import pytest
from conftest import parse_sse
from sqlalchemy import select
from test_chat_workspace_api import make_paper, make_workspace, query_model  # noqa: F401 (a fixture)

from app.core import each_paper
from app.models import LLMOutput
from app.providers.llm_fake import FAKE_WORKSPACE_TOKENS, FakeLLM

pytestmark = pytest.mark.anyio

QUESTION = "How does each paper retrieve?"


@pytest.fixture
def records_in_test_transaction(session, monkeypatch, query_model):  # noqa: F811 (the imported fixture)
    @asynccontextmanager
    async def same():
        yield session

    monkeypatch.setattr(each_paper, "SessionLocal", same)


async def ask(client, workspace, **extra):
    response = await client.post(
        f"/api/workspaces/{workspace.id}/chat", json={"question": QUESTION, "each_paper": True, **extra}
    )
    return response, parse_sse(response.text) if response.status_code == 200 else []


async def test_each_paper_streams_a_reading_per_paper_before_the_sources(
    client, session, fake_llm, records_in_test_transaction
):
    first, second = await make_paper(session, "DPR"), await make_paper(session, "BERT")
    workspace = await make_workspace(session, [first, second])

    response, events = await ask(client, workspace)

    assert response.status_code == 200
    names = [name for name, _ in events]
    assert names == ["reading", "reading", "sources"] + ["token"] * len(FAKE_WORKSPACE_TOKENS) + ["done"]
    readings = [data for name, data in events if name == "reading"]
    assert {r["label"] for r in readings} == {"DPR", "BERT"}
    assert [r["done"] for r in readings] == [1, 2] and {r["total"] for r in readings} == {2}
    assert all(r["status"] == "found" and r["cached"] is False and len(r["cited"]) == 1 for r in readings)


async def test_the_answer_cites_the_records_passages_and_is_saved_with_its_readings(
    client, session, fake_llm, records_in_test_transaction
):
    first, second = await make_paper(session, "DPR"), await make_paper(session, "BERT")
    workspace = await make_workspace(session, [first, second])

    _, events = await ask(client, workspace)

    sources = next(data for name, data in events if name == "sources")
    readings = [data for name, data in events if name == "reading"]
    cited = [c for r in readings for c in r["cited"]]
    assert sorted(s["chunk_id"] for s in sources["sources"]) == sorted(cited)
    done = next(data for name, data in events if name == "done")
    answer = await session.get(LLMOutput, done["output_id"])
    assert answer.workspace_id == workspace.id and answer.prompt_version == each_paper.EACH_PAPER_PROMPT_VERSION
    assert len(answer.readings) == 2


async def test_history_shows_the_readings_of_an_each_paper_answer(
    client, session, fake_llm, records_in_test_transaction
):
    first, second = await make_paper(session, "DPR"), await make_paper(session, "BERT")
    workspace = await make_workspace(session, [first, second])
    await ask(client, workspace)

    [answer] = (await client.get(f"/api/workspaces/{workspace.id}/chat")).json()

    assert sorted(r["label"] for r in answer["readings"]) == ["BERT", "DPR"]
    reading = answer["readings"][0]
    assert reading["status"] == "found" and reading["answer"] == "The paper addresses this."
    assert len(reading["cited"]) == 1 and set(reading["cited"][0]) >= {"chunk_id", "page", "text"}


async def test_a_second_ask_reuses_every_record(client, session, fake_llm, records_in_test_transaction):
    workspace = await make_workspace(session, [await make_paper(session, "DPR")])
    await ask(client, workspace)
    calls = len(fake_llm.calls)

    _, events = await ask(client, workspace)

    [reading] = [data for name, data in events if name == "reading"]
    assert reading["cached"] is True
    assert len(fake_llm.calls) == calls + 1  # the answer only


async def test_paper_chat_refuses_each_paper(client, session, fake_llm, records_in_test_transaction):
    paper = await make_paper(session, "DPR")

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": QUESTION, "each_paper": True})

    assert (response.status_code, response.json()) == (409, {"detail": "each_paper_workspace_only"})


async def test_every_paper_without_text_is_an_error_and_nothing_is_saved(
    client, session, fake_llm, records_in_test_transaction, monkeypatch
):
    """Papers left with no passages to read (a metadata-only paper beside an embedded one, the embedded one's text
    gone by reading time): no model call, an error, nothing saved."""
    workspace = await make_workspace(session, [await make_paper(session, "DPR"), await make_paper(session, "BERT")])
    original = each_paper.plan

    async def textless(*args, **kwargs):
        found = await original(*args, **kwargs)
        tasks = [each_paper.PaperTask(t.paper, [], None) for t in found.tasks]
        return each_paper.Plan(found.workspace_id, found.question, tasks, found.papers_total, found.members, None)

    monkeypatch.setattr(each_paper, "plan", textless)

    _, events = await ask(client, workspace)

    assert [name for name, _ in events] == ["reading", "reading", "error"]
    assert events[-1][1]["message"] == "None of these papers has text to read"
    assert fake_llm.calls == []
    assert not list(await session.scalars(select(LLMOutput).where(LLMOutput.workspace_id == workspace.id)))


async def test_every_reading_failing_is_an_error_and_nothing_is_saved(
    client, session, app, records_in_test_transaction, monkeypatch
):
    from app.api.deps import resolve_llm  # noqa: PLC0415

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(each_paper.claims, "sleep", no_wait)

    class Garbled(FakeLLM):
        async def stream(self, system, prompt):
            yield "not json"

    app.dependency_overrides[resolve_llm] = Garbled
    workspace = await make_workspace(session, [await make_paper(session, "DPR")])

    _, events = await ask(client, workspace)

    assert [name for name, _ in events] == ["reading", "error"]
    assert events[0][1]["status"] == "model_error"
    assert events[-1][1]["message"] == "The model couldn't read any of these papers"
    assert not list(await session.scalars(select(LLMOutput).where(LLMOutput.workspace_id == workspace.id)))


async def test_a_one_paper_workspace_works(client, session, fake_llm, records_in_test_transaction):
    workspace = await make_workspace(session, [await make_paper(session, "DPR")])

    _, events = await ask(client, workspace)

    assert [name for name, _ in events][:2] == ["reading", "sources"] and events[-1][0] == "done"


async def test_without_each_paper_workspace_chat_is_unchanged(client, session, fake_llm, records_in_test_transaction):
    workspace = await make_workspace(session, [await make_paper(session, "DPR"), await make_paper(session, "BERT")])

    response = await client.post(f"/api/workspaces/{workspace.id}/chat", json={"question": QUESTION})

    events = parse_sse(response.text)
    assert events[0][0] == "sources" and "reading" not in [name for name, _ in events]
