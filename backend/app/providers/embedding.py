"""Search embeddings (D150): the built-in model, and the funnel every source's vectors pass through.

The built-in model is nomic-embed-text-v1.5 on ONNX Runtime, read from MODELS_DIR (D134). Until the user downloads it,
load() and get_model() give None and every caller carries on without search (D136). embed_documents / embed_query are
the only entry points for every source: they add its prefix, check that one vector of DIMENSIONS numbers came back per
text, and normalise each one (OpenAI's, Gemini's and the built-in's already are; a compatible server's may not be).
"""

import asyncio
import threading

import numpy as np

from app.config import settings
from app.providers import http_embedders, search_model
from app.providers.base import DIMENSIONS, LLMError, TextEmbedder, WrongDimensions
from app.providers.onnx_embedding import Embedder, normalize

NOMIC_PREFIXES = ("search_document: ", "search_query: ")
# gemini-embedding-2 has no task types: its documented task instructions are text (D154). EmbeddingGemma reads the same.
GEMMA_PREFIXES = ("title: none | text: ", "task: search result | query: ")
WRONG_SIZE = (
    "{model} gives vectors of {size:,} numbers, and PaperLab's search index holds 768. Choose a model that gives 768, "
    "such as nomic-embed-text."
)


def prefixes(model: str) -> tuple[str, str]:
    """(document prefix, question prefix) by model family (D150): nomic-embed-text wherever it runs (the built-in model,
    Ollama, an LM Studio export), Google's gemini-embedding-2 and EmbeddingGemma, and none for the rest."""
    if "nomic-embed-text" in model:
        return NOMIC_PREFIXES
    if model.startswith("gemini-embedding-2") or "embeddinggemma" in model:
        return GEMMA_PREFIXES
    return ("", "")


class BuiltIn:
    """M23's ONNX Embedder as a search source: its sync encode runs in a thread and gives lists. Always nomic's
    prefixes, whatever it is named (tests name it "test")."""

    label = "Built-in"
    is_local = True
    document_prefix, query_prefix = NOMIC_PREFIXES

    def __init__(self, embedder: Embedder, name: str):
        self._embedder = embedder
        self.name = self.model = name  # what chunks record (D137)

    async def encode(self, texts: list[str]) -> list[list[float]]:
        return (await asyncio.to_thread(self._embedder.encode, texts)).tolist()


def load(variant: search_model.Variant | None = None) -> BuiltIn | None:
    """`variant` (the shipped one by default) from MODELS_DIR, or None while either of its files is missing.
    The shipped variant records settings.embed_model; another one its own name, so `evals.run --variant` never records
    one variant's vectors under the other's name."""
    variant = variant or search_model.SHIPPED
    if not search_model.present(settings.models_dir, variant):
        return None
    # Imported here: a process that never embeds (the MCP server answering get_paper) never loads them.
    import onnxruntime
    from tokenizers import Tokenizer

    onnx, tokenizer = (str(search_model.path(settings.models_dir, f)) for f in (variant.onnx, variant.tokenizer))
    session = onnxruntime.InferenceSession(onnx, providers=["CPUExecutionProvider"])
    name = settings.embed_model if variant == search_model.SHIPPED else variant.name
    return BuiltIn(Embedder(session, Tokenizer.from_file(tokenizer)), name)


_load_lock = threading.Lock()
_model: BuiltIn | None = None


def get_model() -> BuiltIn | None:
    """This process's model (the API's and the worker's alike), loaded on first need and kept. None while no search
    model is downloaded: None isn't kept, so the next call looks again and a download that lands later is picked up.

    Two first questions at once each call this on their own thread (asyncio.to_thread); the lock makes the second
    wait for the first load instead of loading a second copy.
    ponytail: the API and the worker each hold a copy of the model. Move query embedding into a shared service only
    if memory becomes a real problem.
    """
    global _model
    with _load_lock:
        if _model is None:
            _model = load()
        return _model


async def _encode(model: TextEmbedder, texts: list[str]) -> list[list[float]]:
    """One unit vector of DIMENSIONS numbers per text, in order, or the reason in words."""
    if not texts:
        return []
    vectors = await model.encode(texts)
    if len(vectors) != len(texts):
        raise LLMError(f"{model.label} answered {len(vectors)} of {len(texts)} texts")
    for vector in vectors:
        if len(vector) != DIMENSIONS:
            raise WrongDimensions(WRONG_SIZE.format(model=model.model, size=len(vector)))
    return normalize(np.asarray(vectors, dtype=np.float64)).tolist()


async def embed_documents(model: TextEmbedder, texts: list[str]) -> list[list[float]]:
    return await _encode(model, [model.document_prefix + text for text in texts])


async def embed_query(model: TextEmbedder, text: str) -> list[float]:
    return (await _encode(model, [model.query_prefix + text]))[0]


def build(source, transport=None) -> TextEmbedder | None:
    """The embedder for a search source (core/embedding_sources.Source), built per question and per job from its
    connection's current values, like build_llm: an edited key applies to the next call. Built-in: this process's
    model, or None until it is downloaded. Under LLM_PROVIDER=fake every connection-based source is
    FakeRemoteEmbedder (M9 decision 13)."""
    if source.kind == "builtin":
        return get_model()
    fake = settings.llm_provider == "fake"
    adapter = http_embedders.FakeRemoteEmbedder if fake else http_embedders.ADAPTERS[source.kind]
    return adapter(source, prefixes(source.model), transport)
