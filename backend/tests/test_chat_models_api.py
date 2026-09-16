import logging
import uuid

import pytest
from conftest import parse_sse
from sqlalchemy import select, update
from test_chat_workspace_api import make_paper, make_workspace

from app.config import settings
from app.core import llm_connections
from app.models import LLMModel, LLMOutput, Paper
from app.providers import embedding, llm

pytestmark = pytest.mark.anyio

KEY = "sk-test-SECRET123"
owner_rows = pytest.mark.xdist_group("llm_connections")


@pytest.fixture
def query_model(embedder, monkeypatch):
    """Workspace chat always retrieves, so the API's process model must be the fake one."""
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)
    return embedder


@pytest.fixture
def fake_stack(monkeypatch):
    """LLM_PROVIDER=fake, without the E2E stack's delay between tokens."""
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(llm, "FAKE_DELAY", 0)


async def model_on(session, name="fake-model", kind="openai_compatible", api_key=KEY) -> tuple[str, uuid.UUID]:
    label = f"Chat connection {uuid.uuid4().hex[:8]}"
    base_url = "https://api.example.com/v1" if kind != "anthropic" else None
    connection = await llm_connections.create_connection(session, kind, label, base_url, api_key)
    model = await llm_connections.add_model(session, connection.id, name)
    return label, model.id


async def paper_and_workspace(session) -> tuple[Paper, str, str]:
    paper = await make_paper(session, "DPR")
    workspace = await make_workspace(session, [paper])
    return paper, f"/api/papers/{paper.id}/chat", f"/api/workspaces/{workspace.id}/chat"


@pytest.mark.parametrize("scope", ["paper", "workspace"])
async def test_an_answer_records_the_chosen_model_and_its_connection(
    client, session, fake_stack, answers_in_test_transaction, query_model, scope
):
    paper, paper_path, workspace_path = await paper_and_workspace(session)
    label, model_id = await model_on(session, "qwen3:8b")

    response = await client.post(
        paper_path if scope == "paper" else workspace_path, json={"question": "why?", "model_id": str(model_id)}
    )

    name, done = parse_sse(response.text)[-1]
    assert (name, done["model"], done["connection_name"]) == ("done", "fake:qwen3:8b", label)
    output = await session.get(LLMOutput, uuid.UUID(done["output_id"]))
    assert (output.model, output.connection_name) == ("fake:qwen3:8b", label)
    history = (await client.get(paper_path if scope == "paper" else workspace_path)).json()
    assert [(a["model"], a["connection_name"]) for a in history] == [("fake:qwen3:8b", label)]


@owner_rows
@pytest.mark.parametrize("scope", ["paper", "workspace"])
async def test_no_model_id_asks_the_default(
    client, session, fake_stack, answers_in_test_transaction, query_model, scope
):
    _, paper_path, workspace_path = await paper_and_workspace(session)
    label, model_id = await model_on(session, "the-default")
    await llm_connections.set_default(session, model_id)

    response = await client.post(paper_path if scope == "paper" else workspace_path, json={"question": "why?"})

    done = parse_sse(response.text)[-1][1]
    assert (done["model"], done["connection_name"]) == ("fake:the-default", label)


@owner_rows
@pytest.mark.parametrize("scope", ["paper", "workspace"])
async def test_an_unknown_model_is_404_and_no_default_is_409_before_anything_else(
    client, session, fake_stack, scope, monkeypatch
):
    paper, paper_path, workspace_path = await paper_and_workspace(session)
    path = paper_path if scope == "paper" else workspace_path
    # Not ready: prepare would answer 409 paper_not_ready or workspace_not_indexed, so a model code shows it ran first.
    await session.execute(update(Paper).where(Paper.id == paper.id).values(status="extracting"))
    retrievals = []
    monkeypatch.setattr("app.core.chat.retrieve", lambda *args, **kwargs: retrievals.append(args))

    unknown = await client.post(path, json={"question": "why?", "model_id": str(uuid.uuid4())})
    await session.execute(update(LLMModel).values(is_default=False))
    no_default = await client.post(path, json={"question": "why?"})

    assert (unknown.status_code, unknown.json()) == (404, {"detail": "model_not_found"})
    assert (no_default.status_code, no_default.json()) == (409, {"detail": "no_model"})
    assert retrievals == []


async def test_renaming_or_deleting_the_connection_never_changes_a_saved_answer(
    client, session, fake_stack, answers_in_test_transaction
):
    paper, paper_path, _ = await paper_and_workspace(session)
    label, model_id = await model_on(session, "qwen3:8b")
    await client.post(paper_path, json={"question": "why?", "model_id": str(model_id)})
    [connection] = await session.scalars(select(LLMModel.connection_id).where(LLMModel.id == model_id))

    renamed = await client.patch(f"/api/llm/connections/{connection}", json={"label": f"{label} renamed"})
    assert renamed.status_code == 200
    assert (await client.delete(f"/api/llm/connections/{connection}")).status_code == 204
    session.add(LLMOutput(paper_id=paper.id, kind="chat", question="old", content="an old answer", model="qwen3:8b",
                          prompt_version=1))
    await session.commit()

    history = (await client.get(paper_path)).json()
    assert [(a["question"], a["model"], a["connection_name"]) for a in history] == [
        ("why?", "fake:qwen3:8b", label),
        ("old", "qwen3:8b", None),  # written before connections existed
    ]


@pytest.mark.parametrize("scope", ["paper", "workspace"])
async def test_a_failing_provider_is_an_error_event_logged_by_label_and_host_without_the_key(
    client, session, provider, query_model, caplog, scope
):
    _, paper_path, workspace_path = await paper_and_workspace(session)
    label, model_id = await model_on(session, "gpt-5-mini")
    if scope == "paper":
        provider.reply("/v1/chat/completions", 401, json={"error": {"message": f"Incorrect API key {KEY}"}})
    else:
        provider.reply("/v1/chat/completions", 500, json={"error": {"message": f"upstream failed for {KEY}"}})
    caplog.set_level(logging.DEBUG)

    response = await client.post(
        paper_path if scope == "paper" else workspace_path, json={"question": "why?", "model_id": str(model_id)}
    )

    name, error = parse_sse(response.text)[-1]
    expected = f"Key rejected by {label}" if scope == "paper" else f"{label} returned 500: upstream failed for ••••"
    assert (name, error) == ("error", {"message": expected, "retryable": True})
    assert provider.requests[0].headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in response.text
    assert KEY not in caplog.text
    assert f"chat answer on {label} (api.example.com) failed: {expected}" in caplog.text


async def test_an_unexpected_exception_mid_answer_is_an_error_event_and_logged(client, session, fake_llm, caplog):
    paper = await make_paper(session, "DPR")

    async def broken(system: str, prompt: str):
        yield "Partial "
        raise RuntimeError("adapter bug")

    fake_llm.stream = broken

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "why?"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources", "token", "error"]
    assert events[-1][1] == {"message": "The answer stopped because of an unexpected error", "retryable": True}
    [record] = [r for r in caplog.records if r.name == "app.api.chat"]
    assert (record.levelno, record.getMessage(), record.exc_info[0]) == (
        logging.ERROR, "chat answer on Fake (fake) failed unexpectedly", RuntimeError
    )
    assert await session.scalar(select(LLMOutput.id).where(LLMOutput.paper_id == paper.id)) is None
