import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select

from app.api import chat as chat_api
from app.core import chat
from app.main import create_app
from app.models import Chunk, LLMOutput, Note, Paper
from app.providers.llm import FAKE_ANSWER, FAKE_TOKENS, FakeLLM, get_llm

pytestmark = pytest.mark.anyio


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        lines = [line for line in block.split("\n") if not line.startswith(":")]  # ": ping" keepalives
        name = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = "\n".join(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


@pytest.fixture
def fake_llm(app, session, monkeypatch):
    fake = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: fake

    @asynccontextmanager
    async def test_session():
        yield session

    # The answer is saved in a fresh session after the stream; keep it inside the test transaction.
    monkeypatch.setattr(chat_api, "SessionLocal", test_session)
    return fake


async def make_paper(session, texts: list[str], status="ready") -> tuple[Paper, list[Chunk]]:
    paper = Paper(title="Chat paper", file_path="/nonexistent.pdf", status=status, page_count=len(texts))
    session.add(paper)
    await session.flush()
    chunks = [
        Chunk(
            paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100, 300, 120]], section_title="Method" if i else None,
            text=text, embed_model="test", strategy_ver=1,
        )
        for i, text in enumerate(texts)
    ]
    session.add_all(chunks)
    await session.commit()
    return paper, chunks


async def outputs_for(session, paper_id) -> list[LLMOutput]:
    return list(await session.scalars(select(LLMOutput).where(LLMOutput.paper_id == paper_id)))


async def test_chat_streams_sources_then_tokens_then_done_and_saves_one_output(client, session, fake_llm):
    paper, chunks = await make_paper(session, ["Intro text.", "Method text."])
    notes_before = await session.scalar(select(func.count()).select_from(Note))

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "  What is the method?  "})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources"] + ["token"] * len(FAKE_TOKENS) + ["done"]
    rect = [[72, 100, 300, 120]]
    assert events[0][1] == {
        "whole_paper": True,
        "sources": [
            {"label": "C1", "chunk_id": str(chunks[0].id), "page": 1, "section": None, "bbox": rect},
            {"label": "C2", "chunk_id": str(chunks[1].id), "page": 2, "section": "Method", "bbox": rect},
        ],
    }
    assert "".join(data["text"] for name, data in events if name == "token") == FAKE_ANSWER

    [output] = await outputs_for(session, paper.id)
    assert events[-1][1] == {"output_id": str(output.id), "model": "fake", "prompt_version": 1, "cited": ["C1"]}
    assert (output.question, output.content, output.model) == ("What is the method?", FAKE_ANSWER, "fake")
    assert (output.source_chunks, output.cited_chunks) == ([c.id for c in chunks], [chunks[0].id])
    assert fake_llm.calls[0][1].rstrip().endswith("Question: What is the method?")
    assert await session.scalar(select(func.count()).select_from(Note)) == notes_before


async def test_llm_error_mid_stream_sends_an_error_event_and_saves_nothing(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text."])
    fake_llm.fail_after = 3

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "why?"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources", "token", "token", "token", "error"]
    assert events[-1][1] == {"message": "fake model failed mid-answer", "retryable": True}
    assert await outputs_for(session, paper.id) == []


async def test_save_failure_sends_an_error_event_instead_of_done(client, session, fake_llm, monkeypatch):
    paper, _ = await make_paper(session, ["Intro text."])

    async def broken_save(*args):
        raise RuntimeError("database went away")

    monkeypatch.setattr(chat, "save_answer", broken_save)

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "why?"})

    events = parse_sse(response.text)
    assert events[-1] == ("error", {"message": "The answer couldn't be saved", "retryable": True})
    assert "done" not in [name for name, _ in events]


async def test_chat_errors_before_streaming_get_status_codes(client, session, fake_llm):
    extracting, _ = await make_paper(session, ["Intro text."], status="extracting")
    unindexed, _ = await make_paper(session, ["x" * 25_000])  # too large to send whole, and no vectors
    ready, _ = await make_paper(session, ["Intro text."])

    async def ask(paper_id, body):
        return await client.post(f"/api/papers/{paper_id}/chat", json=body)

    unknown = await ask(uuid.uuid4(), {"question": "why?"})
    not_ready = await ask(extracting.id, {"question": "why?"})
    not_indexed = await ask(unindexed.id, {"question": "why?"})
    assert (unknown.status_code, not_ready.status_code, not_indexed.status_code) == (404, 409, 409)
    assert (not_ready.json(), not_indexed.json()) == ({"detail": "paper_not_ready"}, {"detail": "paper_not_indexed"})
    for body in [{}, {"question": "   "}, {"question": "x" * 2001}]:
        assert (await ask(ready.id, body)).status_code == 422
    assert fake_llm.calls == []


async def test_history_lists_answers_oldest_first_with_replaced_chunks_as_null(client, session):
    paper, chunks = await make_paper(session, ["Intro text.", "Method text."])
    now = datetime.now(timezone.utc)
    common = {"paper_id": paper.id, "kind": "chat", "model": "qwen3:8b", "prompt_version": 1}
    session.add_all([
        LLMOutput(**common, question="second", content="b [C1]", source_chunks=[chunks[1].id], created_at=now),
        LLMOutput(**common, question="first", content="a [C1][C2]", source_chunks=[c.id for c in chunks],
                  whole_paper=True, created_at=now - timedelta(minutes=1)),
    ])
    await session.commit()
    await session.execute(delete(Chunk).where(Chunk.id == chunks[0].id))  # as a re-ingest would

    response = await client.get(f"/api/papers/{paper.id}/chat")

    assert response.status_code == 200
    first, second = response.json()
    assert (first["question"], first["content"], first["whole_paper"], second["question"]) == (
        "first", "a [C1][C2]", True, "second"
    )
    assert first["sources"] == [
        None,
        {"label": "C2", "chunk_id": str(chunks[1].id), "page": 2, "section": "Method", "bbox": [[72, 100, 300, 120]]},
    ]
    assert second["sources"][0]["label"] == "C1"
    assert {"id", "model", "prompt_version", "created_at"} <= first.keys()
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/chat")).status_code == 404


def test_stream_event_schemas_are_in_openapi():
    """openapi-typescript only generates types for schemas listed in components."""
    schemas = create_app().openapi()["components"]["schemas"]

    for name in ["ChatRequest", "ChatSource", "SourcesEvent", "TokenEvent", "DoneEvent", "ErrorEvent", "ChatAnswer"]:
        assert name in schemas
