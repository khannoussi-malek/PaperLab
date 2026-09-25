"""The search source setting (D151): one row, read per question and per job, its keys kept in model connections."""

import uuid

import pytest
from embedder_fakes import KEY, FakeEmbeddings
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.core import embedding_sources, llm_connections
from app.core.embedding_sources import Source
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import EmbeddingSource
from app.providers import embedding

pytestmark = pytest.mark.anyio


async def test_every_test_starts_on_built_in_whatever_the_owner_chose(session):
    """D159: the dev database (D15) holds the owner's choice. Each test's session sees an empty table of the same shape
    in its own temporary schema instead, so no test reads the owner's source, and none waits on its row's lock."""
    schema = await session.scalar(
        text("SELECT relnamespace::regnamespace::text FROM pg_class WHERE oid = 'embedding_source'::regclass")
    )

    assert schema.startswith("pg_temp")
    assert await session.scalar(select(func.count()).select_from(EmbeddingSource)) == 0
    with pytest.raises(IntegrityError):  # the shadow keeps the table's rules: no Ollama source without a connection
        async with session.begin_nested():
            session.add(EmbeddingSource(kind="ollama", model="nomic-embed-text"))


OPENAI_URL = "https://api.openai.com/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"  # M9's Gemini preset
OPENROUTER_URL = "https://openrouter.ai/api/v1"
LM_STUDIO_URL = "http://host.docker.internal:1234/v1"
OLLAMA_URL = "http://ollama.test:11434"


async def connection(session, kind: str, base_url: str, api_key: str | None = KEY):
    """A connection labelled uniquely: the owner's own share the dev database (D15)."""
    label = f"Search test {uuid.uuid4().hex[:8]}"
    key = None if kind == "ollama" else api_key
    return await llm_connections.create_connection(session, kind, label, base_url, key)


async def test_no_row_means_built_in_under_the_shipped_name(session):
    source = await embedding_sources.active(session)

    assert source == Source(
        kind="builtin", connection_id=None, connection_label=None, base_url=None, api_key=None, model=None,
        name="test", label="Built-in", host=None, is_local=True,
    )  # fmt: skip
    assert await embedding_sources.active_name(session) == "test"  # settings.embed_model, as tests set it


@pytest.mark.parametrize(
    ("kind", "model", "base_url", "name"),
    [
        ("builtin", None, None, "test"),
        ("ollama", "nomic-embed-text", OLLAMA_URL, "ollama/nomic-embed-text"),
        ("openai", "text-embedding-3-small", OPENAI_URL, "openai/text-embedding-3-small@768"),
        ("gemini", "gemini-embedding-2", GEMINI_URL, "gemini/gemini-embedding-2@768"),
        (
            "openai_compatible",
            "text-embedding-nomic-embed-text-v1.5",
            LM_STUDIO_URL,
            "compat/host.docker.internal:1234/text-embedding-nomic-embed-text-v1.5",
        ),
    ],
)
def test_each_source_records_its_own_name(kind, model, base_url, name):
    assert embedding_sources.name_for(kind, model, base_url) == name


async def test_a_saved_source_is_read_with_its_connection_and_starts_a_rebuild(session):
    openai = await connection(session, "openai_compatible", OPENAI_URL)

    await embedding_sources.save(
        session, await embedding_sources.candidate(session, "openai", openai.id, "text-embedding-3-large")
    )
    source = await embedding_sources.active(session)

    assert (source.kind, source.model, source.name, source.label) == (
        "openai", "text-embedding-3-large", "openai/text-embedding-3-large@768", "OpenAI"
    )  # fmt: skip
    assert (source.connection_id, source.connection_label, source.host, source.is_local) == (
        openai.id, openai.label, "api.openai.com", False
    )  # fmt: skip
    assert source.api_key == KEY  # for provider calls only
    assert (source.rebuild_model, source.error) == ("openai/text-embedding-3-large@768", None)
    assert source.rebuild_started_at is not None
    assert "api_key" not in vars(embedding_sources.view(source))


@pytest.mark.parametrize(
    ("kind", "connection_kind", "base_url", "suits"),
    [
        ("openai", "openai_compatible", OPENAI_URL, True),
        ("openai", "openai_compatible", OPENROUTER_URL, False),  # the host decides
        ("gemini", "openai_compatible", GEMINI_URL, True),
        ("gemini", "openai_compatible", OPENAI_URL, False),
        ("ollama", "ollama", OLLAMA_URL, True),
        ("ollama", "openai_compatible", LM_STUDIO_URL, False),  # the kind decides
        ("openai_compatible", "openai_compatible", OPENROUTER_URL, True),
        ("openai_compatible", "ollama", OLLAMA_URL, False),
    ],
)
async def test_which_connections_each_kind_can_use(session, kind, connection_kind, base_url, suits):
    linked = await connection(session, connection_kind, base_url)
    model = "bge-m3" if kind == "openai_compatible" else None

    if suits:
        assert (await embedding_sources.candidate(session, kind, linked.id, model)).connection_id == linked.id
    else:
        names = {"openai": "OpenAI", "gemini": "Gemini", "ollama": "Ollama", "openai_compatible": "OpenAI-compatible"}
        with pytest.raises(InvalidInput, match=f"^{linked.label} can't be used for {names[kind]} search.$"):
            await embedding_sources.candidate(session, kind, linked.id, model)


@pytest.mark.parametrize(
    ("kind", "model", "refusal"),
    [
        (
            "openai",
            "text-embedding-ada-002",
            "text-embedding-ada-002 isn't a search model PaperLab can use with OpenAI.",
        ),
        ("ollama", "llama3", "llama3 isn't a search model PaperLab can use with Ollama."),
        ("gemini", "gemini-embedding-001", "gemini-embedding-001 isn't a search model PaperLab can use with Gemini."),
        ("openai_compatible", None, "Type the name of the model to search with."),
        ("openai_compatible", "  ", "Type the name of the model to search with."),
    ],
)
async def test_only_models_paperlab_can_use_are_accepted(session, kind, model, refusal):
    urls = {"openai": OPENAI_URL, "gemini": GEMINI_URL, "ollama": OLLAMA_URL, "openai_compatible": LM_STUDIO_URL}
    linked = await connection(session, "ollama" if kind == "ollama" else "openai_compatible", urls[kind])

    with pytest.raises(InvalidInput) as refused:
        await embedding_sources.candidate(session, kind, linked.id, model)

    assert str(refused.value) == refusal


async def test_a_pick_without_its_connection_or_with_one_it_does_not_take_is_refused(session):
    ollama = await connection(session, "ollama", OLLAMA_URL)

    with pytest.raises(InvalidInput, match="^Built-in search takes no connection or model.$"):
        await embedding_sources.candidate(session, "builtin", ollama.id, None)
    with pytest.raises(InvalidInput, match="^Choose a connection for this search source.$"):
        await embedding_sources.candidate(session, "ollama", None, None)
    with pytest.raises(NotFound, match="^connection_not_found$"):
        await embedding_sources.candidate(session, "ollama", uuid.uuid4(), None)
    openai = await connection(session, "openai_compatible", OPENAI_URL)
    assert (await embedding_sources.candidate(session, "openai", openai.id, None)).model == "text-embedding-3-small"


async def test_the_fake_stack_names_every_connection_source_fake_and_sends_nothing(session, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    ollama = await connection(session, "ollama", OLLAMA_URL)
    server = FakeEmbeddings()

    source = await embedding_sources.candidate(session, "ollama", ollama.id, None)
    vectors = await embedding.embed_documents(embedding.build(source, server.transport), ["alpha"])

    assert source.name == "fake:ollama/nomic-embed-text"
    assert (await embedding_sources.candidate(session, "builtin", None, None)).name == "test"  # not a connection
    assert (len(vectors[0]), server.requests) == (768, [])


async def test_an_embedding_failure_is_recorded_and_the_next_save_clears_it(session):
    await embedding_sources.record_error(session, "Key rejected by OpenAI")
    recorded = await embedding_sources.active(session)

    await embedding_sources.save(session, recorded)  # a re-index saves the active source again

    assert (recorded.kind, recorded.error) == ("builtin", "Key rejected by OpenAI")
    assert (await embedding_sources.active(session)).error is None


async def test_a_connection_search_uses_cannot_be_deleted(session, client):
    ollama = await connection(session, "ollama", OLLAMA_URL)
    await embedding_sources.save(session, await embedding_sources.candidate(session, "ollama", ollama.id, None))
    sentence = "Search uses this connection. Choose another search source in Settings → Search first."

    with pytest.raises(Conflict, match=f"^{sentence}$"):
        await llm_connections.delete_connection(session, ollama.id)
    refused = await client.delete(f"/api/llm/connections/{ollama.id}")
    await embedding_sources.save(session, await embedding_sources.candidate(session, "builtin", None, None))
    deleted = await client.delete(f"/api/llm/connections/{ollama.id}")

    assert (refused.status_code, refused.json()) == (409, {"detail": sentence})
    assert deleted.status_code == 204
