"""M33: How this was made, and a citation whose passage a re-ingest replaced, over the API."""

import uuid

import pytest
from test_answer_provenance import drafts
from test_chat import make_paper

from app.core import chat, papers
from app.models import LLMOutput, Note, Provenance

pytestmark = pytest.mark.anyio


async def answered(session, paper_id, content="Because [C2].") -> uuid.UUID:
    prepared = await chat.prepare(session, paper_id, "why?")
    return await chat.save_answer(session, paper_id, "why?", prepared, content, "qwen3:8b", "Ollama")


async def test_an_answers_provenance_names_the_model_and_its_cited_passages(client, session):
    paper = await make_paper(session, ["one", "two"])
    output_id = await answered(session, paper.id)

    response = await client.get(f"/api/llm-outputs/{output_id}/provenance")

    assert response.status_code == 200
    body = response.json()
    assert (body["model"], body["connection_name"], body["prompt_version"], body["skill_label"]) == (
        "qwen3:8b",
        "Ollama",
        chat.CHAT_PROMPT_VERSION,
        None,
    )
    assert body["out_of_date"] is False
    assert body["passages"] == [
        {
            "label": "C2",
            "paper_id": str(paper.id),
            "paper_title": "Attention Is All You Need",
            "page": 2,
            "section": "Method",
            "text": "two",
            "state": "current",
        },
    ]


async def test_an_unknown_answer_is_a_404(client):
    response = await client.get(f"/api/llm-outputs/{uuid.uuid4()}/provenance")

    assert response.status_code == 404


async def test_a_citation_whose_chunk_was_replaced_stays_clickable_with_no_box(client, session):
    paper = await make_paper(session, ["one", "two", "three"])
    await answered(session, paper.id, "Because [C2].")
    await papers.replace_chunks(session, paper.id, drafts(["x", "y", "z"]))

    [answer] = (await client.get(f"/api/papers/{paper.id}/chat")).json()

    assert answer["sources"][1] == {
        "label": "C2",
        "chunk_id": None,
        "paper_id": str(paper.id),
        "page": 2,
        "section": "Method",
        "bbox": None,
        "from_abstract": False,
        "replaced": True,
    }
    assert answer["sources"][0] is None


async def test_an_ai_note_shows_its_answers_provenance_and_a_human_note_is_not_ai(client, session):
    paper = await make_paper(session, ["one", "two"])
    output_id = await answered(session, paper.id)
    ai = Note(body="from the answer", provenance=Provenance.LLM, source_id=output_id)
    human = Note(body="mine", provenance=Provenance.HUMAN)
    session.add_all([ai, human])
    await session.commit()

    ok = await client.get(f"/api/notes/{ai.id}/provenance")
    refused = await client.get(f"/api/notes/{human.id}/provenance")

    assert ok.json()["model"] == "qwen3:8b"
    assert refused.status_code == 404
    assert "not_ai" in refused.text


async def test_a_note_added_through_mcp_says_only_where_it_came_from(client, session):
    paper = await make_paper(session, ["one"])
    mcp_output = LLMOutput(paper_id=paper.id, kind="mcp", content="added", model="mcp", prompt_version=0)
    session.add(mcp_output)
    await session.flush()
    note = Note(body="from desktop", provenance=Provenance.LLM, source_id=mcp_output.id)
    session.add(note)
    await session.commit()

    response = await client.get(f"/api/notes/{note.id}/provenance")

    assert response.json() == {"source": "claude_desktop"}
