import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import parse_sse
from sqlalchemy import delete, func, select
from test_chat_workspace import add_note
from test_note_papers import paper_only_note

from app.core import chat
from app.main import create_app
from app.models import Chunk, LLMOutput, Note, Paper
from app.providers import embedding
from app.providers.llm import FAKE_ANSWER, FAKE_NOTES_ANSWER, FAKE_TOKENS

pytestmark = pytest.mark.anyio


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
    paper_id = str(paper.id)
    assert events[0][1] == {
        "whole_paper": True,
        "sources": [
            {"label": "C1", "chunk_id": str(chunks[0].id), "paper_id": paper_id, "page": 1, "section": None,
             "bbox": rect},
            {"label": "C2", "chunk_id": str(chunks[1].id), "paper_id": paper_id, "page": 2, "section": "Method",
             "bbox": rect},
        ],
        "notes": [],
        "notes_used": 0,
        "notes_total": 0,
    }
    assert "".join(data["text"] for name, data in events if name == "token") == FAKE_ANSWER

    [output] = await outputs_for(session, paper.id)
    assert events[-1][1] == {
        "output_id": str(output.id), "model": "fake", "connection_name": "Fake", "prompt_version": 3, "cited": ["C1"]
    }
    assert (output.question, output.content, output.model, output.connection_name) == (
        "What is the method?", FAKE_ANSWER, "fake", "Fake"
    )
    assert (output.source_chunks, output.cited_chunks) == ([c.id for c in chunks], [chunks[0].id])
    assert fake_llm.calls[0][1].rstrip().endswith("Question: What is the method?")
    assert await session.scalar(select(func.count()).select_from(Note)) == notes_before


async def test_paper_chat_sends_the_papers_notes_and_saves_them_with_the_answer(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    note = await add_note(session, paper, "Compare with ELMo.", page=2)

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "What did I note?"})

    sources = parse_sse(response.text)[0][1]
    assert sources["notes"] == [
        {"label": "N1", "note_id": str(note.id), "paper_id": str(paper.id), "page": 2, "provenance": "human"}
    ]
    assert (sources["notes_used"], sources["notes_total"]) == (1, 1)
    assert '[N1] (You · Chat paper p.2) "quote Compare with ELMo." — Compare with ELMo.' in fake_llm.calls[0][1]
    [output] = await outputs_for(session, paper.id)
    assert (output.source_notes, output.notes_used, output.notes_total) == ([note.id], 1, 1)


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


async def test_chat_errors_before_streaming_get_status_codes(client, session, fake_llm, embedder, monkeypatch):
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)  # a search model is downloaded
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


async def test_with_no_search_model_a_long_paper_is_refused_and_a_short_one_still_answers(
    client, session, fake_llm, monkeypatch, answers_in_test_transaction
):
    monkeypatch.setattr(embedding, "get_model", lambda: None)  # nothing downloaded
    long, _ = await make_paper(session, ["x" * 25_000])
    short, _ = await make_paper(session, ["Intro text."])

    refused = await client.post(f"/api/papers/{long.id}/chat", json={"question": "why?"})
    answered = await client.post(f"/api/papers/{short.id}/chat", json={"question": "why?"})

    assert (refused.status_code, refused.json()) == (409, {"detail": "search_not_set_up"})
    assert [name for name, _ in parse_sse(answered.text)][-1] == "done"
    assert len(fake_llm.calls) == 1


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
        {
            "label": "C2", "chunk_id": str(chunks[1].id), "paper_id": str(paper.id), "page": 2, "section": "Method",
            "bbox": [[72, 100, 300, 120]],
        },
    ]
    assert (first["notes"], first["notes_used"], first["notes_total"]) == ([], None, None)
    assert second["sources"][0]["label"] == "C1"
    assert {"id", "model", "prompt_version", "created_at"} <= first.keys()
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/chat")).status_code == 404


async def test_a_follow_up_carries_the_earlier_question_and_is_saved_with_its_parent(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    await client.post(f"/api/papers/{paper.id}/chat", json={"question": "What is the method?"})
    [first] = await outputs_for(session, paper.id)

    response = await client.post(
        f"/api/papers/{paper.id}/chat", json={"question": "And why?", "parent_id": str(first.id)}
    )

    assert parse_sse(response.text)[-1][0] == "done"
    earlier = "Earlier questions in this conversation, oldest first:\n- What is the method?\n\n"
    assert fake_llm.calls[-1][1].endswith(earlier + "Question: And why?\n")
    [follow_up] = [output for output in await outputs_for(session, paper.id) if output.id != first.id]
    assert follow_up.parent_id == first.id
    history = (await client.get(f"/api/papers/{paper.id}/chat")).json()
    # One test transaction: both answers share created_at, so their order isn't checked here.
    assert {(a["question"], a["parent_id"]) for a in history} == {
        ("What is the method?", None), ("And why?", str(first.id))
    }


async def test_a_follow_up_to_a_missing_or_foreign_answer_is_refused_before_streaming(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text."])
    other, _ = await make_paper(session, ["Other text."])
    await client.post(f"/api/papers/{other.id}/chat", json={"question": "Elsewhere?"})
    [foreign] = await outputs_for(session, other.id)

    ask = lambda parent_id: client.post(  # noqa: E731
        f"/api/papers/{paper.id}/chat", json={"question": "And then?", "parent_id": str(parent_id)}
    )
    missing, wrong = await ask(uuid.uuid4()), await ask(foreign.id)

    assert (missing.status_code, missing.json()) == (404, {"detail": "parent_not_found"})
    assert (wrong.status_code, wrong.json()) == (409, {"detail": "parent_scope"})
    assert await outputs_for(session, paper.id) == [] and len(fake_llm.calls) == 1  # only "Elsewhere?" was asked


def test_stream_event_schemas_are_in_openapi():
    """openapi-typescript only generates types for schemas listed in components."""
    schemas = create_app().openapi()["components"]["schemas"]

    for name in ["ChatRequest", "ChatSource", "SourcesEvent", "TokenEvent", "DoneEvent", "ErrorEvent", "ChatAnswer"]:
        assert name in schemas


async def test_a_note_on_the_whole_paper_goes_out_with_no_page(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text."])
    paper_id = paper.id
    note = await paper_only_note(session, paper, body="The whole paper, briefly.")

    response = await client.post(f"/api/papers/{paper_id}/chat", json={"question": "What did I write?"})

    sources = parse_sse(response.text)[0][1]
    expected = [
        {"label": "N1", "note_id": str(note.id), "paper_id": str(paper_id), "page": None, "provenance": "human"}
    ]
    assert sources["notes"] == expected
    [answer] = (await client.get(f"/api/papers/{paper_id}/chat")).json()
    assert answer["notes"] == expected


async def test_a_suggested_note_saves_from_the_stored_answer_and_the_history_knows_it(client, session, fake_llm):
    paper, _ = await make_paper(session, ["Intro text.", "Method text."])
    paper_id = paper.id
    await client.post(f"/api/papers/{paper_id}/chat", json={"question": "Create notes on this paper"})
    [output] = await outputs_for(session, paper_id)
    output_id = output.id  # the refused second save rolls back, which expires `output`

    saved = await client.post(f"/api/chat/answers/{output_id}/notes", json={"index": 0})
    again = await client.post(f"/api/chat/answers/{output_id}/notes", json={"index": 0})

    assert saved.status_code == 201
    note = saved.json()
    assert (note["body"], note["provenance"], note["source_id"]) == (
        "The method anchors every note on a passage [C1].", "llm", str(output_id)
    )
    assert (note["paper_ids"], [anchor["page"] for anchor in note["anchors"]]) == ([str(paper_id)], [1])
    assert (again.status_code, again.json()) == (409, {"detail": "already_saved"})
    [answer] = (await client.get(f"/api/papers/{paper_id}/chat")).json()
    assert answer["content"] == FAKE_NOTES_ANSWER
    assert answer["saved_notes"] == [{"index": 0, "note_id": note["id"], "paper_ids": [str(paper_id)]}]


async def test_saving_a_suggestion_answers_each_refusal_with_its_status(client, session):
    paper, chunks = await make_paper(session, ["Intro text."])
    content = ":::note\n\n:::\n:::note\nIt says so [C1].\n:::"
    output = LLMOutput(paper_id=paper.id, kind="chat", question="notes?", content=content, model="m",
                       prompt_version=3, source_chunks=[chunks[0].id])  # fmt: skip
    session.add(output)
    await session.commit()
    url = f"/api/chat/answers/{output.id}/notes"
    await session.execute(delete(Chunk).where(Chunk.id == chunks[0].id))

    empty = await client.post(url, json={"index": 0})
    stale = await client.post(url, json={"index": 1})
    missing = await client.post(url, json={"index": 2})
    negative = await client.post(url, json={"index": -1})
    unknown = await client.post(f"/api/chat/answers/{uuid.uuid4()}/notes", json={"index": 0})

    assert (empty.status_code, empty.json()) == (422, {"detail": "empty_body"})
    assert (stale.status_code, stale.json()) == (
        422, {"detail": "a cited chunk no longer exists; the paper was re-ingested, so ask again"}
    )
    assert (missing.status_code, missing.json()) == (422, {"detail": "no_such_block"})
    assert negative.status_code == 422
    assert (unknown.status_code, unknown.json()) == (404, {"detail": "answer_not_found"})
