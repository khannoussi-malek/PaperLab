"""The built-in search model: nomic-embed-text-v1.5 on ONNX Runtime (D134), read from MODELS_DIR. Documents and
queries take different prefixes. Until the user downloads the model, load() and get_model() give None, and every
caller carries on without search (D136)."""

import asyncio
import threading

from app.config import settings
from app.providers import search_model
from app.providers.onnx_embedding import Embedder


def load(variant: search_model.Variant | None = None) -> Embedder | None:
    """`variant` (the shipped one by default) from MODELS_DIR, or None while either of its files is missing."""
    variant = variant or search_model.SHIPPED
    if not search_model.present(settings.models_dir, variant):
        return None
    # Imported here: a process that never embeds (the MCP server answering get_paper) never loads them.
    import onnxruntime
    from tokenizers import Tokenizer

    onnx, tokenizer = (str(search_model.path(settings.models_dir, f)) for f in (variant.onnx, variant.tokenizer))
    session = onnxruntime.InferenceSession(onnx, providers=["CPUExecutionProvider"])
    return Embedder(session, Tokenizer.from_file(tokenizer))


_load_lock = threading.Lock()
_model: Embedder | None = None


def get_model() -> Embedder | None:
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


async def _encode(model, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = await asyncio.to_thread(model.encode, texts)
    return vectors.tolist()


async def embed_documents(model, texts: list[str]) -> list[list[float]]:
    return await _encode(model, [f"search_document: {t}" for t in texts])


async def embed_query(model, text: str) -> list[float]:
    return (await _encode(model, [f"search_query: {text}"]))[0]
