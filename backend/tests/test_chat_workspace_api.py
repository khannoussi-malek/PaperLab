import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import parse_sse, unit_vector
from sqlalchemy import delete, insert, select

from app.core import notes
from app.main import create_app
from app.models import Chunk, LLMOutput, Note, Paper, Workspace, workspace_papers
from app.providers import embedding
from app.providers.llm import FAKE_WORKSPACE_ANSWER, FAKE_WORKSPACE_TOKENS

pytestmark = pytest.mark.anyio


@pytest.fixture
def query_model(embedder, monkeypatch):
    """Workspace chat always retrieves, so the API's process model must be the fake one."""
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)
    return embedder


async def make_paper(session, title: str, *, status="ready", embedded=True) -> Paper:
    paper = Paper(title=title, file_path="/nonexistent.pdf", status=status, page_count=2)
    session.add(paper)
    await session.flush()
    texts = [f"{uuid.uuid4().hex} {title} {i}" for i in range(2)]  # unique vectors per run
    session.add_all(
        Chunk(
            paper_id=paper.id, ordinal=i, page=i + 1, bbox=[[72, 100, 300, 120]], section_title=None, text=text,
            embedding=unit_vector(text) if embedded else None, embed_model="test", strategy_ver=1,
        )
        for i, text in enumerate(texts)
    )
    await session.commit()
    return paper


async def make_workspace(session, papers: list[Paper]) -> Workspace:
    workspace = Workspace(name=f"Chat workspace {uuid.uuid4().hex[:6]}")
    session.add(workspace)
    await session.flush()
    if papers:
        rows = [{"workspace_id": workspace.id, "paper_id": p.id} for p in papers]
        await session.execute(insert(workspace_papers), rows)
    await session.commit()
    return workspace


async def note_on(session, paper: Paper, body: str) -> notes.NoteView:
    anchor = notes.Anchor(paper_id=paper.id, page=2, bbox=[(72, 100, 300, 110)], quoted_text="the method")
    return await notes.create_human_note(session, body, anchor)


async def test_workspace_chat_streams_sources_with_notes_then_tokens_then_done(client, session, fake_llm, query_model):
    first, second = await make_paper(session, "DPR"), await make_paper(session, "BERT")
    workspace = await make_workspace(session, [first, second])
    note = await note_on(session, second, "Both use the same encoder.")

    response = await client.post(f"/api/workspaces/{workspace.id}/chat", json={"question": " Compare the methods "})

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources"] + ["token"] * len(FAKE_WORKSPACE_TOKENS) + ["done"]
    sources = events[0][1]
    assert (sources["whole_paper"], sources["notes_used"], sources["notes_total"]) == (False, 1, 1)
    assert [s["label"] for s in sources["sources"]] == ["C1", "C2", "C3", "C4"]
    assert {s["paper_id"] for s in sources["sources"]} == {str(first.id), str(second.id)}
    assert sources["notes"] == [
        {"label": "N1", "note_id": str(note.id), "paper_id": str(second.id), "page": 2, "provenance": "human"}
    ]
    assert "".join(data["text"] for name, data in events if name == "token") == FAKE_WORKSPACE_ANSWER

    [output] = await session.scalars(select(LLMOutput).where(LLMOutput.workspace_id == workspace.id))
    chunk_ids = [uuid.UUID(s["chunk_id"]) for s in sources["sources"]]
    done = {
        "output_id": str(output.id), "model": "fake", "connection_name": "Fake", "prompt_version": 1,
        "cited": ["C1", "C2", "N1"],
    }
    assert events[-1][1] == done
    assert (output.paper_id, output.question, output.content) == (None, "Compare the methods", FAKE_WORKSPACE_ANSWER)
    assert (output.source_chunks, output.cited_chunks) == (chunk_ids, chunk_ids[:2])
    assert (output.source_notes, output.notes_used, output.notes_total) == ([note.id], 1, 1)


async def test_workspace_chat_errors_before_streaming_get_status_codes(client, session, fake_llm, query_model):
    empty = await make_workspace(session, [])
    unindexed = await make_workspace(session, [await make_paper(session, "Old", embedded=False)])
    ready = await make_workspace(session, [await make_paper(session, "New")])
    missing = uuid.uuid4()

    async def ask(workspace_id, body):
        return await client.post(f"/api/workspaces/{workspace_id}/chat", json=body)

    unknown = await ask(missing, {"question": "why?"})
    assert (unknown.status_code, unknown.json()) == (404, {"detail": f"workspace {missing} not found"})
    assert (await ask(empty.id, {"question": "why?"})).json() == {"detail": "workspace_empty"}
    assert (await ask(unindexed.id, {"question": "why?"})).json() == {"detail": "workspace_not_indexed"}
    assert [(await ask(w.id, {"question": "why?"})).status_code for w in (empty, unindexed)] == [409, 409]
    for body in [{}, {"question": "   "}, {"question": "x" * 2001}]:
        assert (await ask(ready.id, body)).status_code == 422
    assert fake_llm.calls == []


async def test_workspace_history_lists_its_answers_with_notes(client, session):
    paper = await make_paper(session, "DPR")
    workspace = await make_workspace(session, [paper])
    kept, deleted = await note_on(session, paper, "kept"), await note_on(session, paper, "deleted")
    chunks = list(await session.scalars(select(Chunk).where(Chunk.paper_id == paper.id).order_by(Chunk.ordinal)))
    now = datetime.now(timezone.utc)
    common = {"kind": "chat", "model": "fake", "prompt_version": 1, "source_chunks": [chunks[0].id]}
    session.add_all([
        LLMOutput(**common, workspace_id=workspace.id, question="second", content="b [N1]", created_at=now,
                  source_notes=[kept.id, deleted.id], notes_used=2, notes_total=5),
        LLMOutput(**common, workspace_id=workspace.id, question="first", content="a [C1]",
                  created_at=now - timedelta(minutes=1), notes_used=0, notes_total=0),
        LLMOutput(**common, paper_id=paper.id, question="single paper", content="c", created_at=now),
    ])
    await session.commit()
    await session.execute(delete(Note).where(Note.id == deleted.id))

    response = await client.get(f"/api/workspaces/{workspace.id}/chat")

    assert response.status_code == 200
    first, second = response.json()
    assert (first["question"], first["notes"], first["notes_used"], first["notes_total"]) == ("first", [], 0, 0)
    assert first["sources"][0]["paper_id"] == str(paper.id)
    assert second["question"] == "second"
    assert second["notes"] == [
        {"label": "N1", "note_id": str(kept.id), "paper_id": str(paper.id), "page": 2, "provenance": "human"},
        None,
    ]
    assert (second["notes_used"], second["notes_total"]) == (2, 5)
    missing = uuid.uuid4()
    assert (await client.get(f"/api/workspaces/{missing}/chat")).json() == {"detail": f"workspace {missing} not found"}


@pytest.mark.parametrize("scope", ["paper", "workspace"])
async def test_the_transaction_ends_before_the_llm_streams(client, session, fake_llm, query_model, monkeypatch, scope):
    """prepare_answer commits in the dependency, so a minutes-long stream holds no pooled connection."""
    paper = await make_paper(session, "DPR")
    workspace = await make_workspace(session, [paper])
    path = f"/api/papers/{paper.id}/chat" if scope == "paper" else f"/api/workspaces/{workspace.id}/chat"
    commits = []
    real_commit = session.commit

    async def spy_commit():
        commits.append(len(fake_llm.calls))  # how many LLM streams had started when this commit ran
        await real_commit()

    monkeypatch.setattr(session, "commit", spy_commit)

    response = await client.post(path, json={"question": "why?"})

    assert parse_sse(response.text)[-1][0] == "done"
    assert commits == [0, 1]  # the dependency's commit before streaming, then save_answer's


def test_workspace_schemas_are_in_openapi():
    schemas = create_app().openapi()["components"]["schemas"]

    for name in ["NoteSource", "WorkspaceOut", "WorkspaceCreate", "WorkspaceRename"]:
        assert name in schemas
    assert "workspace_ids" in schemas["PaperOut"]["required"]
