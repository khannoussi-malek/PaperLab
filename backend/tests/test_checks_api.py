"""POST /api/notes/{id}/check (SSE) and GET /api/papers/{id}/checks (M22 spec §3.7)."""
# ruff: noqa: F811 (pytest fixtures are imported, then named as parameters)

import uuid

import pytest
from conftest import parse_sse
from sqlalchemy import delete, select, update
from test_briefs_api import HEADINGS, fake_stack  # noqa: F401
from test_chat_models_api import owner_rows
from test_checks import SUMMARY, long_paper, note_on
from test_remote_confirm import _remote
from test_sections import paper_with_headings

from app.api.deps import resolve_check_llm
from app.core import checks, embedding_index, llm_connections
from app.models import Chunk, LLMConnection, LLMModel, LLMOutput, Note, PaperMerge, Provenance
from app.providers import embedding
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
    paper, note = await a_note(session)
    app.dependency_overrides[resolve_check_llm] = lambda: FakeLLM(fail_after=3)

    events = parse_sse((await check(client, note.id)).text)

    assert [name for name, _ in events] == ["sources", "token", "error"]  # one kept line got out first
    assert await rows(session, paper) == []


async def test_a_note_deleted_mid_stream_sends_an_error_and_saves_nothing(client, session, app, fake_llm):
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


async def test_each_refusal_comes_before_the_ones_after_it(client, session, fake_llm):
    """Notes with two faults: the one earlier in the documented order is the one said."""
    assert (await check(client, uuid.uuid4())).status_code == 404
    paper, _ = await paper_with_headings(session, HEADINGS)
    five_cs = "Category:\nContext:\nCorrectness:\nContributions:\nClarity:"

    async def refused(note, status, detail):
        response = await check(client, note.id)
        assert (response.status_code, response.json()["detail"]) == (status, detail)

    await refused(await note_on(session, paper, kind="assumption", provenance=Provenance.LLM), 409, "not_your_text")
    await refused(await note_on(session, paper, "a" * 8_001, kind="assumption"), 422, "not_checkable")
    await refused(await note_on(session, paper, five_cs, kind="five_cs", linked=False), 422, "nothing_written")
    await refused(await note_on(session, paper, "a" * 8_001, linked=False), 422, "note_too_long")
    await refused(await note_on(session, paper, linked=False), 409, "note_not_on_one_paper")
    nopdf, _ = await paper_with_headings(session, HEADINGS, has_pdf=False, status="extracting")
    await refused(await note_on(session, nopdf), 409, "needs_full_text")
    unready, _ = await paper_with_headings(session, HEADINGS, status="extracting")
    await refused(await note_on(session, unready), 409, "paper_not_ready")
    back, _ = await paper_with_headings(session, ["References", "References"])
    await refused(await note_on(session, back), 409, "lens_empty")


async def test_a_merged_paper_is_gone_and_an_unknown_one_not_found(client, session):
    gone, kept = uuid.uuid4(), uuid.uuid4()
    session.add(PaperMerge(kept_id=kept, merged_id=gone, status="merged"))
    await session.flush()

    merged = await client.get(f"/api/papers/{gone}/checks")

    assert merged.status_code == 410 and merged.json()["detail"] == "paper_merged"
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/checks")).status_code == 404


async def long_note(session, **kw):
    paper, _ = await long_paper(session, **kw)
    return paper, await note_on(session, paper)


@pytest.fixture
def search_model(embedder, monkeypatch):
    """The route reads the search model from get_model; hand it the test embedder."""
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)


async def test_a_long_paper_with_no_search_model_is_409(client, session, fake_llm, monkeypatch):
    monkeypatch.setattr(embedding, "get_model", lambda: None)
    _, note = await long_note(session)

    response = await check(client, note.id)

    assert (response.status_code, response.json()["detail"]) == (409, "search_not_set_up")


async def test_a_long_paper_with_no_vectors_is_409_not_indexed(client, session, fake_llm, search_model):
    _, note = await long_note(session, embedded=False)

    assert (await check(client, note.id)).json()["detail"] == "paper_not_indexed"


async def test_a_long_paper_mid_rebuild_is_409_rebuilding(client, session, fake_llm, search_model, monkeypatch):
    paper, note = await long_note(session)

    async def rebuilding(*_):
        return embedding_index.Rebuild(done=1, total=2)

    async def waiting(*_):
        return [paper.id]

    monkeypatch.setattr(embedding_index, "rebuild", rebuilding)
    monkeypatch.setattr(embedding_index, "pending_in", waiting)

    assert (await check(client, note.id)).json()["detail"] == "search_rebuilding"


async def test_vectors_from_another_model_are_409(client, session, fake_llm, search_model):
    paper, note = await long_note(session)
    await session.execute(update(Chunk).where(Chunk.paper_id == paper.id).values(embed_model="an-older-model"))
    await session.commit()

    assert (await check(client, note.id)).json()["detail"] == "embedding_model_changed"


async def test_a_note_that_mentions_notes_still_gets_the_check_reply(client, session, fake_llm):
    # the fake answers a check first: a reader's note may say "notes" after a "Question: "
    paper, note = await a_note(session, body=f"{SUMMARY}\nQuestion: where are my notes?")

    events = parse_sse((await check(client, note.id)).text)

    assert [name for name, _ in events] == ["sources", "token", "token", "token", "done"]


async def test_done_cites_kept_lines_only(client, session, app, fake_llm):
    class DroppedCitesC2(FakeLLM):
        async def stream(self, system, prompt):
            yield "Missing: the main result [C1].\nHere is a better summary you could use [C2].\n"

    paper, note = await a_note(session)
    app.dependency_overrides[resolve_check_llm] = lambda: DroppedCitesC2()

    events = parse_sse((await check(client, note.id)).text)

    assert len(events[0][1]["sources"]) >= 2
    assert events[-1][1]["cited"] == ["C1"]
    [row] = await rows(session, paper)
    assert len(row.cited_chunks) == 1


@owner_rows
async def test_an_unknown_model_is_not_found_and_no_default_is_a_conflict(client, session, fake_stack):
    _, note = await a_note(session)

    unknown = await check(client, note.id, model_id=str(uuid.uuid4()))
    await session.execute(update(LLMModel).values(is_default=False))
    no_default = await check(client, note.id)

    assert (unknown.status_code, unknown.json()["detail"]) == (404, "model_not_found")
    assert (no_default.status_code, no_default.json()["detail"]) == (409, "no_model")


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
async def test_a_remote_default_asks_first(client, session, app, answers_in_test_transaction, fake_stack):
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
    fake_stack,
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
    fake_stack,
):
    paper, note = await a_note(session)
    await _remote(session)
    local = await add_model(session, "ollama", "http://localhost:11434")

    response = await check(client, note.id, model_id=str(local.id))

    done = parse_sse(response.text)[-1]
    assert response.status_code == 200 and done[0] == "done"
    assert done[1]["model"] == "fake:m"  # the picked model ran, not the remote default "big"
    assert len(await rows(session, paper)) == 1


@remote
async def test_confirm_remote_streams(client, session, answers_in_test_transaction, fake_stack):
    paper, note = await a_note(session)
    await _remote(session)

    response = await check(client, note.id, confirm_remote=True)

    assert response.status_code == 200 and parse_sse(response.text)[-1][0] == "done"


@remote
async def test_a_confirmed_picked_remote_model_is_the_one_that_runs(
    client,
    session,
    local_default_model,
    answers_in_test_transaction,
    fake_stack,
):
    _, note = await a_note(session)
    picked = await add_model(session, "openai_compatible", "https://api.example.com/v1")

    response = await check(client, note.id, model_id=str(picked.id), confirm_remote=True)

    assert parse_sse(response.text)[-1][1]["model"] == "fake:m"


@remote
async def test_the_model_that_was_checked_is_the_one_that_runs(
    client,
    session,
    local_default_model,
    answers_in_test_transaction,
    fake_stack,
    monkeypatch,
):
    """A second lookup that turned up a cloud default must not decide: the local model the gate saw runs."""
    _, note = await a_note(session)
    cloud = await add_model(session, "openai_compatible", "https://api.example.com/v1")
    cloud.name = "cloud"
    real, seen = llm_connections.resolve, []

    async def flipping(session, model_id):
        seen.append(model_id)
        return await real(session, model_id if len(seen) == 1 else cloud.id)

    monkeypatch.setattr(llm_connections, "resolve", flipping)

    response = await check(client, note.id)

    assert response.status_code == 200
    assert parse_sse(response.text)[-1][1]["model"] == f"fake:{local_default_model.name}"


@remote
async def test_a_refused_model_is_said_before_the_note_is_read(
    client,
    session,
    answers_in_test_transaction,
    fake_stack,
):
    await _remote(session)

    response = await check(client, uuid.uuid4())

    assert response.status_code == 409 and response.json()["detail"] == "remote_model_needs_confirm"
