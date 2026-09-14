import asyncio
import functools
import json
from collections.abc import AsyncIterator

import anthropic
import httpx
import httpx2

from app.config import settings
from app.providers.base import LLM, LLMError, LLMUnavailable

# Streaming, so a generous cap costs nothing when unused and never truncates a long answer.
ANTHROPIC_MAX_TOKENS = 64_000
# Cold model loads take 7-10 s before the first line; httpx's default 5 s read timeout is too short.
OLLAMA_TIMEOUT = httpx.Timeout(120, connect=5)
# ponytail: Ollama defaults to a 4096-token context, which truncates from the head and drops the system
# prompt on a whole-paper prompt (SMALL_PAPER_CHARS=24_000 chars is ~5-6k tokens). KV-cache memory grows
# with context; lower this together with SMALL_PAPER_CHARS if memory is tight.
OLLAMA_NUM_CTX = 16_384


class OllamaLLM:
    def __init__(self, model: str, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.model = model
        self.base_url = base_url
        self._transport = transport  # tests pass httpx.MockTransport

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": True,
            # Thinking models (qwen3, deepseek-r1) otherwise stream empty content while they think.
            "think": False,
            "options": {"num_ctx": OLLAMA_NUM_CTX},
        }
        client = httpx.AsyncClient(base_url=self.base_url, timeout=OLLAMA_TIMEOUT, transport=self._transport)
        try:
            async with client, client.stream("POST", "/api/chat", json=body) as response:
                if response.status_code == 404:
                    raise LLMUnavailable(f"Model {self.model} isn't installed (ollama pull {self.model})")
                if response.is_error:
                    await response.aread()
                    raise LLMError(f"Ollama returned {response.status_code}: {response.text}")
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    # A failure after the 200 arrives as an error line; the status can't change any more.
                    if "error" in data:
                        raise LLMError(f"Ollama: {data['error']}")
                    if content := data.get("message", {}).get("content"):
                        yield content
                    if data.get("done"):
                        return
        except httpx.ConnectError as exc:
            raise LLMUnavailable(f"Can't reach Ollama at {self.base_url}") from exc
        except (httpx.HTTPError, ValueError) as exc:  # ValueError: a line that isn't JSON
            raise LLMError(f"Ollama request failed: {exc}") from exc


class AnthropicLLM:
    def __init__(self, model: str, api_key: str, http_client=None):
        self.model = model
        # http_client: tests pass an httpx2.AsyncClient with httpx2.MockTransport (SDK 1.x runs on httpx2).
        self._client = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable("Can't reach the Anthropic API") from exc
        except anthropic.NotFoundError as exc:
            raise LLMUnavailable(f"Model {self.model} isn't available on the Anthropic API") from exc
        # The base class on purpose: an overload mid-stream arrives as APIStatusError with status 200.
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        # A transport drop mid-stream (not an SSE `error` event): the SDK only wraps errors from the
        # initial send, so a read failure during iteration surfaces as a raw httpx2 exception.
        except httpx2.HTTPError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc


FAKE_ANSWER = "Fake answer: the method is described here [C1]."
# Word by word, with the citation marker split across two tokens like a real model does.
FAKE_TOKENS = ["Fake ", "answer: ", "the ", "method ", "is ", "described ", "here ", "[C", "1]", "."]


class FakeLLM:
    """Deterministic, offline. LLM_PROVIDER=fake selects it, so the E2E stack answers without a model."""

    model = "fake"

    def __init__(self, fail_after: int | None = None, delay: float = 0.0):
        self.fail_after = fail_after  # raise LLMError after this many tokens
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((system, prompt))
        for index, token in enumerate(FAKE_TOKENS):
            if index == self.fail_after:
                raise LLMError("fake model failed mid-answer")
            await asyncio.sleep(self.delay)
            yield token


@functools.cache
def get_llm() -> LLM:
    """The configured provider, built once per process. Chat routes depend on it, so tests override it."""
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model, settings.anthropic_api_key)
    if settings.llm_provider == "fake":
        # A small delay so the E2E stack streams visibly instead of in one burst.
        return FakeLLM(delay=0.05)
    return OllamaLLM(settings.llm_model, settings.ollama_url)
