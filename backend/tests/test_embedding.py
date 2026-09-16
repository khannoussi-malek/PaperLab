import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.providers import embedding

pytestmark = pytest.mark.anyio

ENCODE_ARGS = {"batch_size": 16, "normalize_embeddings": True}


async def test_documents_get_the_document_prefix(embedder):
    vectors = await embedding.embed_documents(embedder, ["alpha", "beta"])

    assert embedder.calls == [(["search_document: alpha", "search_document: beta"], ENCODE_ARGS)]
    assert len(vectors) == 2 and len(vectors[0]) == 768 and type(vectors[0][0]) is float


async def test_queries_get_the_query_prefix_and_are_normalized(embedder):
    vector = await embedding.embed_query(embedder, "what is attention?")

    assert embedder.calls == [(["search_query: what is attention?"], ENCODE_ARGS)]
    assert len(vector) == 768


async def test_no_texts_never_calls_the_model(embedder):
    assert await embedding.embed_documents(embedder, []) == []
    assert embedder.calls == []


def test_the_api_model_loads_once_per_process(monkeypatch):
    loads = []
    monkeypatch.setattr(embedding, "load", lambda: loads.append("load") or object())
    embedding._load_once.cache_clear()
    try:
        assert embedding.get_model() is embedding.get_model()
    finally:
        embedding._load_once.cache_clear()
    assert loads == ["load"]


def test_two_first_questions_at_once_share_one_load(monkeypatch):
    loads = []

    def slow_load():
        loads.append("load")
        time.sleep(0.2)  # long enough for the second thread to arrive while the first still loads
        return object()

    monkeypatch.setattr(embedding, "load", slow_load)
    embedding._load_once.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(lambda _: embedding.get_model(), range(2))
    finally:
        embedding._load_once.cache_clear()
    assert loads == ["load"]
    assert first is second


def test_no_test_can_load_the_real_model():
    """conftest's autouse fixture stops an unmocked chat or retrieval from downloading 523 MB."""
    embedding._load_once.cache_clear()
    with pytest.raises(RuntimeError, match="tests must not load the embedding model"):
        embedding.get_model()
