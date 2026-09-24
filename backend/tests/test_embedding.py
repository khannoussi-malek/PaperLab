import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from onnx_fakes import FakeSession, ids, tiny_tokenizer

from app.config import settings
from app.providers import embedding, search_model
from app.providers.base import DIMENSIONS, LLMError, WrongDimensions
from app.providers.embedding import BuiltIn, prefixes
from app.providers.onnx_embedding import Embedder

pytestmark = pytest.mark.anyio

REAL_LOAD = embedding.load  # conftest's autouse fixture replaces it once each test starts


NOMIC = ("search_document: ", "search_query: ")
GEMMA = ("title: none | text: ", "task: search result | query: ")


class WideSession(FakeSession):
    """FakeSession's four numbers per token, padded with zeros to the 768 the search index holds."""

    def run(self, output_names, feed):
        (tokens,) = super().run(output_names, feed)
        return [np.pad(tokens, ((0, 0), (0, 0), (0, DIMENSIONS - tokens.shape[-1])))]


class Stub:
    """A search source whose answer the test decides."""

    name = model = "stub-model"
    label = "Stub"
    is_local = True
    document_prefix, query_prefix = "d: ", "q: "

    def __init__(self, vectors):
        self.vectors = vectors
        self.calls: list[list[str]] = []

    async def encode(self, texts):
        self.calls.append(texts)
        return self.vectors


@pytest.fixture
def not_loaded(monkeypatch):
    """This process has loaded no model yet."""
    monkeypatch.setattr(embedding, "_model", None)


async def test_documents_get_the_document_prefix(embedder):
    vectors = await embedding.embed_documents(embedder, ["alpha", "beta"])

    assert embedder.calls == [(["search_document: alpha", "search_document: beta"], {})]
    assert len(vectors) == 2 and len(vectors[0]) == 768 and type(vectors[0][0]) is float


async def test_queries_get_the_query_prefix(embedder):
    vector = await embedding.embed_query(embedder, "what is attention?")

    assert embedder.calls == [(["search_query: what is attention?"], {})]
    assert len(vector) == 768


async def test_the_model_sees_each_prefix_and_gives_unit_vectors():
    """Through BuiltIn over the real Embedder: the prefix reaches the tokenizer, and each vector comes back
    normalised."""
    session = WideSession()
    model = BuiltIn(Embedder(session, tiny_tokenizer()), "test")

    [document] = await embedding.embed_documents(model, ["Alpha"])
    query = await embedding.embed_query(model, "beta")

    assert [feed["input_ids"].tolist() for _, feed in session.runs] == [
        [ids("[CLS]", "search", "_", "document", ":", "alpha", "[SEP]")],
        [ids("[CLS]", "search", "_", "query", ":", "beta", "[SEP]")],
    ]
    assert type(document[0]) is float
    assert np.isclose(np.linalg.norm(document), 1.0) and np.isclose(np.linalg.norm(query), 1.0)


async def test_no_texts_never_calls_the_model(embedder):
    assert await embedding.embed_documents(embedder, []) == []
    assert embedder.calls == []


def test_with_no_model_downloaded_load_gives_none(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "models_dir", tmp_path)  # nothing downloaded here

    assert REAL_LOAD() is None


def test_the_model_loads_once_per_process(monkeypatch, not_loaded):
    loads = []
    monkeypatch.setattr(embedding, "load", lambda: loads.append("load") or object())

    assert embedding.get_model() is embedding.get_model()
    assert loads == ["load"]


def test_no_model_is_not_kept_so_a_later_download_is_picked_up(monkeypatch, not_loaded, embedder):
    found = [None, embedder]  # nothing downloaded yet, then the download lands
    monkeypatch.setattr(embedding, "load", lambda: found.pop(0))

    assert embedding.get_model() is None
    assert embedding.get_model() is embedder
    assert embedding.get_model() is embedder  # kept now: a third load would find the list empty


def test_two_first_questions_at_once_share_one_load(monkeypatch, not_loaded):
    loads = []

    def slow_load():
        loads.append("load")
        time.sleep(0.2)  # long enough for the second thread to arrive while the first still loads
        return object()

    monkeypatch.setattr(embedding, "load", slow_load)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda _: embedding.get_model(), range(2))
    assert loads == ["load"]
    assert first is second


def test_no_test_can_load_the_real_model(not_loaded):
    """conftest's autouse fixture stops an unmocked chat or retrieval from loading the search model."""
    with pytest.raises(RuntimeError, match="tests must not load the embedding model"):
        embedding.get_model()


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (search_model.SHIPPED.name, NOMIC),  # the built-in model
        ("nomic-embed-text", NOMIC),  # Ollama
        ("text-embedding-nomic-embed-text-v1.5", NOMIC),  # LM Studio's export
        ("gemini-embedding-2", GEMMA),
        ("embeddinggemma:300m", GEMMA),
        ("text-embedding-3-small", ("", "")),
        ("bge-m3", ("", "")),  # a model PaperLab knows nothing about
    ],
)
def test_each_model_family_gets_its_own_prefixes(model, expected):
    assert prefixes(model) == expected


def test_the_built_in_model_is_a_local_source_with_nomic_prefixes_whatever_its_name():
    model = BuiltIn(Embedder(WideSession(), tiny_tokenizer()), "test")

    assert (model.name, model.model, model.label, model.is_local) == ("test", "test", "Built-in", True)
    assert (model.document_prefix, model.query_prefix) == NOMIC


async def test_every_vector_comes_out_at_unit_length():
    stub = Stub([[3.0] + [0.0] * 767, [0.0, 4.0] + [0.0] * 766])  # lengths 3 and 4

    vectors = await embedding.embed_documents(stub, ["a", "b"])

    assert stub.calls == [["d: a", "d: b"]]
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    assert vectors[0][0] == pytest.approx(1.0) and vectors[1][1] == pytest.approx(1.0)


async def test_one_vector_per_text_or_the_answer_is_refused():
    with pytest.raises(LLMError, match="^Stub answered 1 of 2 texts$"):
        await embedding.embed_documents(Stub([[1.0] * 768]), ["a", "b"])


async def test_a_vector_that_is_not_768_long_is_refused_in_words():
    with pytest.raises(WrongDimensions) as refused:
        await embedding.embed_query(Stub([[0.1] * 1024]), "q")

    assert str(refused.value) == (
        "stub-model gives vectors of 1,024 numbers, and PaperLab's search index holds 768. Choose a model that gives "
        "768, such as nomic-embed-text."
    )
