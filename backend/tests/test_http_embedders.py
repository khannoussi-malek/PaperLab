"""The search sources behind a model connection (D152–D155): what each one sends, its batches, its retries and its
failures, against FakeEmbeddings. No network."""

import logging

import numpy as np
import pytest
from embedder_fakes import KEY, FakeEmbeddings, source, vector

from app.config import settings
from app.providers import embedding, http_embedders
from app.providers.base import LLMError, LLMUnavailable, ModelNotPulled, WrongDimensions

pytestmark = pytest.mark.anyio


@pytest.fixture
def server():
    return FakeEmbeddings()


@pytest.fixture
def waits(monkeypatch):
    """Every retry's wait, in seconds, instead of sleeping."""
    seen: list[float] = []

    async def record(seconds: float) -> None:
        seen.append(seconds)

    monkeypatch.setattr(http_embedders, "_sleep", record)
    return seen


def built(kind: str, server: FakeEmbeddings, **fields):
    return embedding.build(source(kind, **fields), server.transport)


def sent(texts: list[str], prefix: str = "") -> np.ndarray:
    """What the funnel gives back for FakeEmbeddings' answers: the same vectors at unit length (they come at 2)."""
    return np.array([vector(prefix + text, 768) for text in texts]) / 2


async def test_openai_asks_for_768_numbers_with_the_key_and_keeps_the_order(server):
    texts = ["alpha", "beta", "gamma"]

    vectors = await embedding.embed_documents(built("openai", server), texts)

    [request] = server.requests
    assert str(request.url) == "https://api.openai.com/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert server.bodies() == [
        {"model": "text-embedding-3-small", "input": texts, "encoding_format": "float", "dimensions": 768}
    ]
    assert np.allclose(vectors, sent(texts))  # the answer came in reverse index order


async def test_a_compatible_server_gets_no_dimensions_and_no_key_header_without_a_key(server):
    await embedding.embed_documents(
        built("openai_compatible", server, model="nomic-embed-text-v1.5", api_key=None), ["alpha"]
    )

    [request] = server.requests
    assert str(request.url) == "http://vllm.test:8000/v1/embeddings"
    assert "authorization" not in request.headers
    # vLLM refuses `dimensions` for a model not trained to shorten (D153); nomic's prefixes follow the model's name.
    assert server.bodies() == [
        {"model": "nomic-embed-text-v1.5", "input": ["search_document: alpha"], "encoding_format": "float"}
    ]


async def test_ollama_sends_nomic_embed_text_with_truncation(server):
    await embedding.embed_documents(built("ollama", server), ["alpha"])

    [request] = server.requests
    assert str(request.url) == "http://ollama.test:11434/api/embed"
    assert server.bodies() == [{"model": "nomic-embed-text", "input": ["search_document: alpha"], "truncate": True}]


@pytest.mark.parametrize(("kind", "count", "batches"), [("openai", 129, [128, 1]), ("ollama", 33, [32, 1])])
async def test_texts_go_in_batches_one_after_another_and_come_back_in_order(server, kind, count, batches):
    texts = [f"text {i}" for i in range(count)]

    vectors = await embedding.embed_documents(built(kind, server), texts)

    assert [len(body.get("input") or body.get("requests")) for body in server.bodies()] == batches
    assert np.allclose(vectors, sent(texts, embedding.prefixes(source(kind).model)[0]))


async def test_a_rejected_key_says_so_and_the_key_is_in_no_message_or_log_record(server, caplog):
    caplog.set_level(logging.DEBUG)
    server.statuses = [401]

    with pytest.raises(LLMUnavailable, match="^Key rejected by OpenAI$") as refused:
        await embedding.embed_query(built("openai", server), "q")

    assert KEY not in str(refused.value) and KEY not in caplog.text
    assert len(server.requests) == 1  # a rejected key isn't tried again


async def test_a_refusal_that_echoes_the_key_is_shown_masked(server):
    server.statuses = [400]

    with pytest.raises(LLMError) as refused:
        await embedding.embed_query(built("openai", server), "q")

    assert str(refused.value) == "OpenAI returned 400: Incorrect API key provided: ••••"


async def test_a_429_waits_what_retry_after_says_then_goes_on(server, waits):
    server.statuses = [429]  # with Retry-After: 2

    await embedding.embed_documents(built("openai", server), ["alpha"])

    assert (len(server.requests), waits) == (2, [2.0])


async def test_four_429s_give_up_in_words(server, waits):
    server.statuses = [429] * 4

    with pytest.raises(LLMError) as refused:
        await embedding.embed_documents(built("openai", server), ["alpha"])

    assert str(refused.value) == (
        "OpenAI is limiting requests (429), and PaperLab gave up after 4 tries. Try again in a few minutes."
    )
    assert (len(server.requests), waits) == (4, [2.0, 2.0, 2.0])


async def test_server_errors_and_dropped_reads_wait_1_2_4_seconds_then_say_what_the_server_said(server, waits):
    server.statuses = [503, "drop", 503, 503]

    with pytest.raises(LLMError, match="^OpenAI returned 503: Incorrect API key provided: ••••$"):
        await embedding.embed_documents(built("openai", server), ["alpha"])

    assert (len(server.requests), waits) == (4, [1.0, 2.0, 4.0])


async def test_a_model_that_gives_the_wrong_size_is_refused_in_words(server):
    server.dims = 1024

    with pytest.raises(WrongDimensions) as refused:
        await embedding.embed_documents(built("openai_compatible", server), ["alpha"])

    assert str(refused.value) == (
        "bge-m3 gives vectors of 1,024 numbers, and PaperLab's search index holds 768. Choose a model that gives 768, "
        "such as nomic-embed-text."
    )


async def test_ollama_without_the_model_says_it_is_not_pulled(server):
    server.not_pulled = True

    with pytest.raises(ModelNotPulled, match="^nomic-embed-text isn't in Ollama yet$"):
        await embedding.embed_query(built("ollama", server), "q")


async def test_a_refused_connection_is_not_tried_again(server, waits):
    server.statuses = ["refuse"]

    with pytest.raises(LLMUnavailable, match="^Can't reach ollama.test$"):
        await embedding.embed_query(built("ollama", server), "q")

    assert (len(server.requests), waits) == (1, [])


async def test_an_answer_without_vectors_is_an_error_in_words(server):
    server.statuses = [200]  # a 200 whose body is an error message

    with pytest.raises(LLMError, match="^OpenAI sent an answer PaperLab can't read$"):
        await embedding.embed_query(built("openai", server), "q")


async def test_the_fake_stack_embeds_offline_under_the_source_name(server, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    model = built("openai", server, name="fake:openai/text-embedding-3-small@768")

    first = await embedding.embed_query(model, "q")

    assert (type(model).__name__, model.name, server.requests) == (
        "FakeRemoteEmbedder", "fake:openai/text-embedding-3-small@768", []
    )  # fmt: skip
    assert first == await embedding.embed_query(model, "q") and len(first) == 768
