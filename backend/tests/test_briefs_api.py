"""POST /api/papers/{id}/briefs/{lens} (SSE) and GET /api/papers/{id}/briefs (M16 spec §4.3)."""

import logging
import uuid

import pytest
from conftest import parse_sse
from sqlalchemy import select, update
from test_chat_api import make_paper
from test_chat_models_api import model_on, owner_rows
from test_sections import paper_with_headings

from app.config import settings
from app.core import briefs, chat
from app.main import create_app
from app.models import LLMModel, LLMOutput
from app.providers import llm
from app.providers.llm import FAKE_ANSWER, FAKE_TOKENS

pytestmark = pytest.mark.anyio

HEADINGS = ["Abstract", "1 Introduction", "2 Method", "3 Conclusion"]


@pytest.fixture
def fake_stack(monkeypatch):
    """LLM_PROVIDER=fake without the E2E stack's delay, as in test_chat_models_api: the chosen model is resolved."""
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(llm, "FAKE_DELAY", 0)


async def generate(client, paper_id, lens="key_ideas", model_id=None):
    params = None if model_id is None else {"model_id": str(model_id)}
    return await client.post(f"/api/papers/{paper_id}/briefs/{lens}", params=params)


async def test_a_brief_streams_like_a_chat_answer_and_is_saved(client, session, fake_llm):
    paper, chunks = await paper_with_headings(session, HEADINGS)

    response = await generate(client, paper.id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources"] + ["token"] * len(FAKE_TOKENS) + ["done"]
    sources = events[0][1]
    assert (sources["whole_paper"], sources["notes"], sources["notes_used"], sources["notes_total"]) == (
        True,
        [],
        None,
        None,
    )
    assert [s["chunk_id"] for s in sources["sources"]] == [str(chunks[i].id) for i in (0, 1, 3)]
    [output] = list(await session.scalars(select(LLMOutput).where(LLMOutput.paper_id == paper.id)))
    assert events[-1][1] == {
        "output_id": str(output.id),
        "model": "fake",
        "connection_name": "Fake",
        "prompt_version": 1,
        "cited": ["C1"],
    }
    assert (output.kind, output.lens, output.content) == ("brief", "key_ideas", FAKE_ANSWER)
    assert fake_llm.calls[0][0] == briefs.SYSTEM_PROMPT


async def test_briefs_list_the_newest_per_lens_with_stale_and_partial(client, session, fake_llm):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    await generate(client, paper.id)

    response = await client.get(f"/api/papers/{paper.id}/briefs")

    assert response.status_code == 200
    [brief] = response.json()
    assert (brief["lens"], brief["content"], brief["model"], brief["connection_name"], brief["prompt_version"]) == (
        "key_ideas",
        FAKE_ANSWER,
        "fake",
        "Fake",
        1,
    )
    assert (brief["stale"], brief["partial"]) == (False, False)
    assert [s["label"] for s in brief["sources"]] == ["C1", "C2", "C3"]
    assert brief["sources"][0]["chunk_id"] == str(chunks[0].id)


async def test_a_brief_is_refused_before_streaming(client, session, fake_llm):
    paper, _ = await paper_with_headings(session, HEADINGS)
    extracting, _ = await paper_with_headings(session, HEADINGS, status="extracting")
    no_pdf, _ = await paper_with_headings(session, ["Abstract"], has_pdf=False)

    unknown = await generate(client, uuid.uuid4())
    not_ready = await generate(client, extracting.id)
    empty = await generate(client, paper.id, "related")
    needs_pdf = await generate(client, no_pdf.id)
    full = await generate(client, paper.id, "full")
    bogus = await generate(client, paper.id, "bogus")

    assert [r.status_code for r in (unknown, not_ready, empty, needs_pdf, full, bogus)] == [
        404,
        409,
        409,
        409,
        422,
        422,
    ]
    assert [r.json() for r in (not_ready, empty, needs_pdf, full)] == [
        {"detail": "paper_not_ready"},
        {"detail": "lens_empty"},
        {"detail": "needs_full_text"},
        {"detail": "lens_not_briefable"},
    ]
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/briefs")).status_code == 404
    assert fake_llm.calls == []


async def test_a_model_error_mid_brief_sends_an_error_event_and_saves_nothing(client, session, fake_llm):
    paper, _ = await paper_with_headings(session, HEADINGS)
    fake_llm.fail_after = 3

    events = parse_sse((await generate(client, paper.id)).text)

    assert [name for name, _ in events] == ["sources", "token", "token", "token", "error"]
    assert events[-1][1] == {"message": "fake model failed mid-answer", "retryable": True}
    assert (await client.get(f"/api/papers/{paper.id}/briefs")).json() == []


async def test_a_brief_that_cant_be_saved_says_so(client, session, fake_llm, monkeypatch):
    paper, _ = await paper_with_headings(session, HEADINGS)

    async def broken_save(*args):
        raise RuntimeError("database went away")

    monkeypatch.setattr(briefs, "save_brief", broken_save)

    events = parse_sse((await generate(client, paper.id)).text)

    assert events[-1] == ("error", {"message": "The brief couldn't be saved", "retryable": True})
    assert "done" not in [name for name, _ in events]


def save_failure_log(caplog) -> tuple[int, str]:
    [record] = [r for r in caplog.records if r.name == "app.api.chat" and r.getMessage().startswith("saving")]
    return record.levelno, record.getMessage()


async def test_a_failed_save_logs_what_it_was_saving(client, session, fake_llm, monkeypatch, caplog):
    # stream_output is shared, so chat's line is pinned here too: word for word what it was before briefs (R5).
    paper, _ = await paper_with_headings(session, HEADINGS)
    chat_paper, _ = await make_paper(session, ["Intro text."])

    async def broken_save(*args):
        raise RuntimeError("database went away")

    monkeypatch.setattr(briefs, "save_brief", broken_save)
    monkeypatch.setattr(chat, "save_answer", broken_save)

    await generate(client, paper.id)
    brief_log = save_failure_log(caplog)
    caplog.clear()
    await client.post(f"/api/papers/{chat_paper.id}/chat", json={"question": "why?"})

    assert brief_log == (logging.ERROR, f"saving a brief for paper {paper.id}, lens key_ideas failed")
    assert save_failure_log(caplog) == (
        logging.ERROR,
        f"saving a chat answer for {chat.Scope(paper_id=chat_paper.id)} failed",
    )


async def test_an_unexpected_exception_mid_brief_is_an_error_event(client, session, fake_llm):
    paper, _ = await paper_with_headings(session, HEADINGS)

    async def broken(system: str, prompt: str):
        yield "Partial "
        raise RuntimeError("adapter bug")

    fake_llm.stream = broken

    events = parse_sse((await generate(client, paper.id)).text)

    assert events[-1] == ("error", {"message": "The brief stopped because of an unexpected error", "retryable": True})


async def test_a_brief_records_the_chosen_model(client, session, fake_stack, answers_in_test_transaction):
    paper, _ = await paper_with_headings(session, HEADINGS)
    label, model_id = await model_on(session, "qwen3:8b")

    events = parse_sse((await generate(client, paper.id, model_id=model_id)).text)

    assert (events[-1][1]["model"], events[-1][1]["connection_name"]) == ("fake:qwen3:8b", label)


@owner_rows
async def test_an_unknown_model_is_404_and_no_default_is_409_before_the_brief_is_prepared(client, session, fake_stack):
    # Not ready: prepare would answer 409 paper_not_ready, so a model code shows the model was resolved first.
    paper, _ = await paper_with_headings(session, HEADINGS, status="extracting")

    unknown = await generate(client, paper.id, model_id=uuid.uuid4())
    await session.execute(update(LLMModel).values(is_default=False))
    no_default = await generate(client, paper.id)

    assert (unknown.status_code, unknown.json()) == (404, {"detail": "model_not_found"})
    assert (no_default.status_code, no_default.json()) == (409, {"detail": "no_model"})


def test_the_brief_schemas_are_in_openapi():
    schemas = create_app().openapi()["components"]["schemas"]

    assert "BriefOut" in schemas  # the brief takes no body: its model is the optional ?model_id= query
