"""P1: while search is rebuilt with a new source it pauses with how far it got (D156), and a question the source can't
embed says why (D155). Each test hides the owner's chunks in its own transaction (D15), so a rebuild counts only this
test's papers. Questions embed with a fake named after the active source: no request leaves."""

import uuid

import pytest
from conftest import FakeEmbedder, unit_vector
from sqlalchemy import delete, text, update
from test_embedding_index import worker_uses

from app.config import settings
from app.core import chat, embedding_index, embedding_sources, library, llm_connections, retrieval, workspaces
from app.core.errors import Conflict
from app.models import Chunk, Paper
from app.providers import embedding
from app.workers import ingest

pytestmark = pytest.mark.anyio

OLLAMA_NAME = "ollama/nomic-embed-text"
LONG = 15_000  # two chunks of this are past chat.SMALL_PAPER_CHARS: chat on the paper searches


@pytest.fixture
async def just_ours(session):
    """The dev database (D15) holds the owner's chunks: hidden here, so a rebuild counts only this test's papers."""
    await session.execute(delete(Chunk))
    return session


async def paper_with(session, model: str | None, chunk_chars: int = LONG) -> Paper:
    """A ready paper of two chunks whose vectors came from `model` (None: none yet). Long by default."""
    paper = Paper(title=f"Rebuild {uuid.uuid4().hex[:8]}", file_path="/nonexistent.pdf", status="ready", page_count=1)
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(
            paper_id=paper.id, ordinal=i, page=1, bbox=[[72, 100, 300, 120]],
            text=f"{paper.title} {i} " + "x" * chunk_chars,
            embedding=None if model is None else unit_vector(f"{paper.title} {i}"), embed_model=model or "test",
            strategy_ver=1,
        )
        for i in range(2)
    )  # fmt: skip
    await session.commit()
    return paper


async def switched(session) -> embedding_sources.Source:
    """Search switched to a new Ollama connection. The rebuild starts at the transaction's frozen now(), so every paper
    this test made before counts ("at or before")."""
    label = f"Ollama {uuid.uuid4().hex[:8]}"
    connection = await llm_connections.create_connection(session, "ollama", label, "http://ollama.test:11434", None)
    await embedding_sources.save(session, await embedding_sources.candidate(session, "ollama", connection.id, None))
    return await embedding_sources.active(session)


def asked(source: embedding_sources.Source) -> FakeEmbedder:
    return FakeEmbedder(name=source.name, label=source.label)


def rebuilding(source: embedding_sources.Source, done: int, total: int) -> dict:
    """The Conflict's details: what the MCP tool passes on."""
    papers = "paper" if total == 1 else "papers"
    detail = f"Search is being rebuilt with {source.label}: {done} of {total} {papers}. Try again when it finishes."
    return {"detail": detail, "done": done, "total": total}


async def test_mid_rebuild_a_long_paper_not_yet_re_embedded_pauses_with_how_far_it_got(just_ours):
    await paper_with(just_ours, OLLAMA_NAME)  # already on the new source
    waiting = await paper_with(just_ours, "test")
    source = await switched(just_ours)

    with pytest.raises(Conflict, match="^search_rebuilding$") as paused:
        await chat.prepare(just_ours, waiting.id, "q", embedder=asked(source))

    assert await embedding_index.rebuild(just_ours, source) == embedding_index.Rebuild(done=1, total=2)
    assert paused.value.details == rebuilding(source, 1, 2)


async def test_mid_rebuild_workspace_chat_and_library_search_pause(just_ours):
    moved = await paper_with(just_ours, OLLAMA_NAME)
    waiting = await paper_with(just_ours, "test")
    source = await switched(just_ours)
    workspace = await workspaces.create(just_ours, f"Rebuild {uuid.uuid4().hex[:8]}")
    for paper in (moved, waiting):
        await workspaces.add_paper(just_ours, workspace.id, paper.id)

    with pytest.raises(Conflict, match="^search_rebuilding$") as in_workspace:
        await chat.prepare(just_ours, chat.Scope(workspace_id=workspace.id), "q", embedder=asked(source))
    with pytest.raises(Conflict, match="^search_rebuilding$") as in_library:
        await library.search(just_ours, "q", embedder=asked(source))

    assert in_workspace.value.details == in_library.value.details == rebuilding(source, 1, 2)


async def test_mid_rebuild_a_paper_already_moved_answers_and_a_short_one_goes_whole(just_ours):
    moved = await paper_with(just_ours, OLLAMA_NAME)
    await paper_with(just_ours, "test")  # still waiting: the rebuild is on
    short = await paper_with(just_ours, "test", chunk_chars=100)
    source = await switched(just_ours)
    question = asked(source)

    answered = await chat.prepare(just_ours, moved.id, "q", embedder=question)
    whole = await chat.prepare(just_ours, short.id, "q", embedder=question)

    assert answered.whole_paper is False and {s.paper_id for s in answered.sources} == {moved.id}
    assert whole.whole_paper is True
    assert question.calls == [(["search_query: q"], {})]  # only the long paper searched


async def test_a_paper_added_after_the_switch_neither_counts_nor_pauses(just_ours):
    await paper_with(just_ours, OLLAMA_NAME)
    await paper_with(just_ours, "test")
    source = await switched(just_ours)
    late = await paper_with(just_ours, None)  # uploaded after the switch, still being embedded
    await just_ours.execute(
        update(Paper).where(Paper.id == late.id).values(created_at=text("now() + interval '1 minute'"))
    )
    question = asked(source)

    assert await embedding_index.rebuild(just_ours, source) == embedding_index.Rebuild(done=1, total=2)
    assert await retrieval.searchable(just_ours, [late.id], question) is question


async def test_a_renamed_built_in_asks_for_a_re_index_instead_of_a_rebuild(just_ours, monkeypatch):
    """M23's D137 case: a release renames the built-in model. rebuild_model is the old name, so no rebuild nobody
    started: the old vectors read as another model's and Settings shows its Re-index prompt, as before M25."""
    monkeypatch.setattr(settings, "embed_model", "nomic-ai/nomic-embed-text-v1.5")
    old = await paper_with(just_ours, "nomic-ai/nomic-embed-text-v1.5")
    await embedding_sources.save(just_ours, await embedding_sources.active(just_ours))  # a re-index then
    monkeypatch.setattr(settings, "embed_model", "test")  # the new release's name
    source = await embedding_sources.active(just_ours)

    with pytest.raises(Conflict, match="^embedding_model_changed$"):
        await chat.prepare(just_ours, old.id, "q", embedder=asked(source))
    assert await embedding_index.rebuild(just_ours, source) is None


async def test_the_last_re_embed_ends_the_rebuild_and_search_answers_again(just_ours, monkeypatch):
    moved = await paper_with(just_ours, OLLAMA_NAME)
    waiting = await paper_with(just_ours, "test")
    source = await switched(just_ours)
    worker_uses(just_ours, monkeypatch)

    await ingest.reembed_paper({"embedder": asked(source)}, str(waiting.id), True)

    assert await embedding_index.rebuild(just_ours, source) is None
    found = await library.search(just_ours, "q", embedder=asked(source))
    assert {passage.paper_id for passage in found} == {moved.id, waiting.id}


async def test_the_chat_route_answers_409_search_rebuilding(client, just_ours, fake_llm, monkeypatch):
    await paper_with(just_ours, OLLAMA_NAME)
    waiting = await paper_with(just_ours, "test")
    await switched(just_ours)
    monkeypatch.setattr(embedding, "build", lambda source, transport=None: asked(source))

    response = await client.post(f"/api/papers/{waiting.id}/chat", json={"question": "why?"})

    # The app reads how far it got from GET /api/embedding (Correction 6).
    assert (response.status_code, response.json()) == (409, {"detail": "search_rebuilding"})
    assert fake_llm.calls == []


async def test_a_question_the_source_cannot_embed_is_a_409_in_words(client, just_ours, fake_llm, monkeypatch):
    paper = await paper_with(just_ours, "test")  # Built-in, every chunk embedded
    monkeypatch.setattr(embedding, "get_model", lambda: FakeEmbedder(label="OpenAI", refuse="Key rejected by OpenAI"))

    response = await client.post(f"/api/papers/{paper.id}/chat", json={"question": "why?"})

    assert (response.status_code, response.json()) == (
        409, {"detail": "Search couldn't embed your question: Key rejected by OpenAI."}
    )  # fmt: skip
    assert fake_llm.calls == []
