"""nomic-embed-text-v1.5 via sentence-transformers. Documents and queries take different prefixes."""

import asyncio
import functools
import threading

from app.config import settings

# Peak memory ~1.2 GB at 16; the Docker VM has 7.65 GiB shared by two stacks.
BATCH_SIZE = 16


def load():
    # Imported here: torch takes seconds to import, and the API only needs it on its first chat.
    # No trust_remote_code: the Hub's remote code crashes on encode under transformers 5, and the
    # built-in NomicBert produces identical vectors.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embed_model)


_load_lock = threading.Lock()


def get_model():
    """The API's query embedder, loaded on first use.

    Two first questions at once each call this on their own thread (asyncio.to_thread); the lock makes the second
    wait for the first load instead of loading a second copy.
    ponytail: the API and the worker each hold a copy of the model (~0.6-1.2 GB). Move query
    embedding into a shared service only if memory becomes a real problem.
    """
    with _load_lock:
        return _load_once()


@functools.cache
def _load_once():
    return load()


async def _encode(model, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    # normalize_embeddings: the model has no Normalize module, so vectors come back with norm ~20.
    vectors = await asyncio.to_thread(model.encode, texts, batch_size=BATCH_SIZE, normalize_embeddings=True)
    return vectors.tolist()


async def embed_documents(model, texts: list[str]) -> list[list[float]]:
    return await _encode(model, [f"search_document: {t}" for t in texts])


async def embed_query(model, text: str) -> list[float]:
    return (await _encode(model, [f"search_query: {text}"]))[0]
