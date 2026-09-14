"""What chat needs from a language model. Implementations: OllamaLLM, AnthropicLLM, FakeLLM (providers/llm.py)."""

from collections.abc import AsyncIterator
from typing import Protocol


class LLMUnavailable(Exception):
    """The provider can't be reached or the model isn't installed. The message is shown to the user."""


class LLMError(Exception):
    """Anything else that stops an answer. The message is shown to the user."""


class LLM(Protocol):
    model: str

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]: ...
