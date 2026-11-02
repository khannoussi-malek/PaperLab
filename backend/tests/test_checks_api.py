"""POST /api/notes/{id}/check (SSE) and GET /api/papers/{id}/checks (M22 spec §3.7)."""

import uuid

import pytest
from conftest import parse_sse
from sqlalchemy import delete, select
from test_briefs_api import HEADINGS, fake_stack  # noqa: F401
from test_checks import note_on
from test_remote_confirm import _remote
from test_sections import paper_with_headings

from app.core import checks
from app.models import LLMConnection, LLMModel, LLMOutput, Note, Provenance
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio

PROPERTIES = {
    "CheckOut": {
        "id", "note_id", "lines", "dropped", "sources", "whole_paper", "model", "connection_name", "prompt_version",
        "created_at", "stale",
    },
    "CheckLineOut": {"verdict", "text"},
}  # fmt: skip
BANNED = {"content", "raw", "reply", "suggestion", "rewrite", "replacement", "wording"}


async def check(client, note_id, **body):
    return await client.post(f"/api/notes/{note_id}/check", json=body)


async def a_note(session, **kw):
    paper, _ = await paper_with_headings(session, HEADINGS)
    return paper, await note_on(session, paper, **kw)


async def rows(session, paper):
    return list(
        await session.scalars(select(LLMOutput).where(LLMOutput.paper_id == paper.id, LLMOutput.kind == "check"))
    )


async def test_a_check_streams_only_kept_lines_and_is_saved(client, session, fake_llm):
    paper, note = await a_note(session)

    response = await check(client, note.id)

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources", "token", "token", "token", "done"]
    sources = events[0][1]
    assert (sources["notes"], sources["notes_used"], sources["notes_total"]) == ([], None, None)
    assert events[-1][1]["cited"] == ["C1"]
    [row] = await rows(session, paper)
    assert events[-1][1]["output_id"] == str(row.id)
    reply = checks.parse_check(row.content, len(row.source_chunks), checks.guard_for(note.body, ["Text of chunk 0."]))
    assert (len(reply.lines), reply.dropped) == (3, 1)
    assert fake_llm.calls[0][0] == checks.SYSTEM_PROMPT


async def test_a_failing_model_sends_an_error_and_saves_nothing(client, session, app, fake_llm):
    from app.api.deps import resolve_check_llm

    paper, note = await a_note(session)
    app.dependency_overrides[resolve_check_llm] = lambda: FakeLLM(fail_after=1)

    events = parse_sse((await check(client, note.id)).text)

    assert [name for name, _ in events] == ["sources", "error"]
    assert await rows(session, paper) == []


async def test_a_note_deleted_mid_stream_sends_an_error_and_saves_nothing(client, session, app, fake_llm):
    from app.api.deps import resolve_check_llm

    class Deleting(FakeLLM):
        async def stream(self, system, prompt):
            await session.execute(delete(Note))
            async for token in super().stream(system, prompt):
                yield token

    paper, note = await a_note(session)
    app.dependency_overrides[resolve_check_llm] = lambda: Deleting()

    events = parse_sse((await check(client, note.id)).text)

    assert events[-1][0] == "error"
    assert await rows(session, paper) == []


async def test_the_raw_reply_never_leaves_the_server(client, session, fake_llm):
    paper, note = await a_note(session)

    posted = await check(client, note.id)
    listed = await client.get(f"/api/papers/{paper.id}/checks")

    [row] = await rows(session, paper)
    assert "better summary" in row.content
    assert "better summary" not in posted.text and "better summary" not in listed.text
    [one] = listed.json()
    assert "content" not in one and one["stale"] is False
    assert [(line["verdict"]) for line in one["lines"]] == ["missing", "unsupported", "supported"] and one[
        "dropped"
    ] == 1


def test_check_routes_expose_only_these_properties():
    from app.main import create_app

    schemas = create_app().openapi()["components"]["schemas"]
    for name, expected in PROPERTIES.items():
        found = set(schemas[name]["properties"])
        assert found == expected and not found & BANNED


async def test_every_refusal_is_in_the_documented_order(client, session, fake_llm):
    assert (await check(client, uuid.uuid4())).status_code == 404
    paper, _ = await paper_with_headings(session, HEADINGS)
    ai = await note_on(session, paper, provenance=Provenance.LLM)
    assert (await check(client, ai.id)).json()["detail"] == "not_your_text"
    other = await note_on(session, paper, kind="assumption")
    assert (await check(client, other.id)).status_code == 422
    empty = await note_on(
        session, paper, body="Category:\nContext:\nCorrectness:\nContributions:\nClarity:", kind="five_cs"
    )
    assert (await check(client, empty.id)).status_code == 422
    long = await note_on(session, paper, body="a" * 8_001)
    assert (await check(client, long.id)).status_code == 422
    loose = await note_on(session, paper, linked=False)
    assert (await check(client, loose.id)).json()["detail"] == "note_not_on_one_paper"
    unready, _ = await paper_with_headings(session, HEADINGS, status="extracting")
    assert (await check(client, (await note_on(session, unready)).id)).json()["detail"] == "paper_not_ready"
    nopdf, _ = await paper_with_headings(session, HEADINGS, has_pdf=False)
    assert (await check(client, (await note_on(session, nopdf)).id)).json()["detail"] == "needs_full_text"
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/checks")).status_code == 404


async def test_an_unknown_model_is_not_found(client, session, fake_stack, local_default_model):  # noqa: F811
    _, note = await a_note(session)
    assert (await check(client, note.id, model_id=str(uuid.uuid4()))).json()["detail"] == "model_not_found"


async def add_model(session, kind, base_url, default=False):
    connection = LLMConnection(kind=kind, label=f"C {uuid.uuid4().hex[:6]}", base_url=base_url)
    session.add(connection)
    await session.flush()
    model = LLMModel(connection_id=connection.id, name="m", is_default=default)
    session.add(model)
    await session.flush()
    return model


remote = pytest.mark.xdist_group("manuscript_rows")


@remote
async def test_a_remote_default_asks_first(client, session, app, answers_in_test_transaction, fake_stack):  # noqa: F811
    paper, note = await a_note(session)
    await _remote(session)

    response = await check(client, note.id)

    assert response.status_code == 409 and response.json()["detail"] == "remote_model_needs_confirm"
    assert response.json()["host"] == "api.example.com"
    assert await rows(session, paper) == []


@remote
async def test_a_picked_remote_model_asks_even_with_a_local_default(
    client,
    session,
    local_default_model,
    answers_in_test_transaction,
    fake_stack,  # noqa: F811
):
    _, note = await a_note(session)
    picked = await add_model(session, "openai_compatible", "https://api.example.com/v1")

    response = await check(client, note.id, model_id=str(picked.id))

    assert response.status_code == 409 and response.json()["detail"] == "remote_model_needs_confirm"


@remote
async def test_a_picked_local_model_runs_with_a_remote_default(
    client,
    session,
    answers_in_test_transaction,
    fake_stack,  # noqa: F811
):
    paper, note = await a_note(session)
    await _remote(session)
    local = await add_model(session, "ollama", "http://localhost:11434")

    response = await check(client, note.id, model_id=str(local.id))

    assert response.status_code == 200 and parse_sse(response.text)[-1][0] == "done"
    assert len(await rows(session, paper)) == 1


@remote
async def test_confirm_remote_streams(client, session, answers_in_test_transaction, fake_stack):  # noqa: F811
    paper, note = await a_note(session)
    await _remote(session)

    response = await check(client, note.id, confirm_remote=True)

    assert response.status_code == 200 and parse_sse(response.text)[-1][0] == "done"


@remote
async def test_a_refused_model_is_said_before_the_note_is_read(
    client,
    session,
    answers_in_test_transaction,
    fake_stack,  # noqa: F811
):
    await _remote(session)

    response = await check(client, uuid.uuid4())

    assert response.status_code == 409 and response.json()["detail"] == "remote_model_needs_confirm"
