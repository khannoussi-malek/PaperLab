"""What chat needs from a language model. Implementations: OllamaLLM, OpenAICompatibleLLM, AnthropicLLM, FakeLLM
(providers/llm.py), built per question by build_llm."""

from collections.abc import AsyncIterator
from typing import Protocol


class LLMUnavailable(Exception):
    """The provider can't be reached, rejects the key, or lacks the model. The message is shown to the user."""


class LLMError(Exception):
    """Anything else that stops an answer. The message is shown to the user."""


class LLM(Protocol):
    model: str
    connection_name: str  # the connection's label when the adapter was built; saved with each answer
    host: str  # where requests go, for log lines

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]: ...
