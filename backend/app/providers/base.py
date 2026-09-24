"""What chat needs from a language model (LLM) and what search needs from an embedding source (TextEmbedder).
Chat's implementations are in providers/llm.py, built per question by build_llm; search's are the built-in model
(providers/embedding.BuiltIn) and the connection-based ones (providers/http_embedders), built by embedding.build."""

from collections.abc import AsyncIterator
from typing import Protocol


class LLMUnavailable(Exception):
    """The provider can't be reached, rejects the key, or lacks the model. The message is shown to the user."""


class LLMError(Exception):
    """Anything else that stops an answer. The message is shown to the user."""


class WrongDimensions(LLMError):
    """A search source's vectors aren't DIMENSIONS long (D153). The message says so in words."""


class ModelNotPulled(LLMUnavailable):
    """Ollama doesn't have the embedding model yet (D152): Settings offers to pull it."""


# vector(768) fixes the size of every stored vector: every search source must give exactly this many numbers (D131).
DIMENSIONS = 768


class LLM(Protocol):
    model: str
    connection_name: str  # the connection's label when the adapter was built; saved with each answer
    host: str  # where requests go, for log lines

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]: ...


class TextEmbedder(Protocol):
    """A search source (D150). Callers never call encode: embedding.embed_documents / embed_query add the prefix,
    check the answer and normalise it."""

    name: str  # what chunks.embed_model records
    label: str  # in messages: Built-in, OpenAI, Gemini, or the connection's own label
    model: str  # the model's own name, in messages
    is_local: bool
    document_prefix: str
    query_prefix: str

    async def encode(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in order. The texts already carry their prefix."""
        ...
