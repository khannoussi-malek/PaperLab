"""Chat adapters, one per connection kind, and each provider's model list.

`connection` is anything with a connection's kind, label, base_url and api_key (an LLMConnection row). Messages name
the connection and its host, never the key: some providers echo a rejected key in their error body.
"""

import asyncio
import functools
import json
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import anthropic
import httpx
import httpx2

from app.config import settings
from app.core.chat import WORKSPACE_SYSTEM_PROMPT
from app.providers.base import LLM, LLMError, LLMUnavailable

# Cold model loads take 7-10 s before the first line; httpx's default 5 s read timeout is too short. Local
# OpenAI-compatible servers (LM Studio, vLLM, llama.cpp) load models the same way.
OLLAMA_TIMEOUT = httpx.Timeout(120, connect=5)
# A model list is quick everywhere; a long wait means a wrong address, not a loading model.
LIST_TIMEOUT = httpx.Timeout(15, connect=5)
# ponytail: Ollama defaults to a 4096-token context, which truncates from the head and drops the system
# prompt on a whole-paper prompt (SMALL_PAPER_CHARS=24_000 chars is ~5-6k tokens). KV-cache memory grows
# with context; lower this together with SMALL_PAPER_CHARS if memory is tight.
OLLAMA_NUM_CTX = 16_384
ANTHROPIC_HOST = "api.anthropic.com"
KEY_MASK = "••••"
PROVIDER_MESSAGE_CHARS = 300


def host_of(base_url: str | None) -> str:
    return ANTHROPIC_HOST if base_url is None else (urlsplit(base_url).hostname or base_url)


def masked(text: str, api_key: str | None) -> str:
    return text.replace(api_key, KEY_MASK) if api_key else text


def provider_message(text: str, api_key: str | None = None) -> str:
    """The provider's own error message from a body (`{"error": {"message"}}`, `{"error": "…"}` or plain text), key
    masked before anything is cut, so a cut can't leave part of the key."""
    text = masked(text, api_key)
    try:
        body = json.loads(text)
    except ValueError:
        return text.strip()[:PROVIDER_MESSAGE_CHARS]
    error = body.get("error", body) if isinstance(body, dict) else body
    if isinstance(error, dict):
        error = error.get("message", error)
    return str(error)[:PROVIDER_MESSAGE_CHARS]


def http_error(label: str, status: int, text: str, api_key: str | None, model: str | None = None) -> Exception:
    """A failed response in words: a rejected key, a missing model (when `model` is given), else status + message."""
    if status in (401, 403):
        return LLMUnavailable(f"Key rejected by {label}")
    if status == 404 and model is not None:
        return LLMUnavailable(f"Model {model} isn't available on {label}")
    return LLMError(f"{label} returned {status}: {provider_message(text, api_key)}")


def _bearer(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class OllamaLLM:
    def __init__(self, model: str, base_url: str, connection_name: str = "Ollama", transport=None):
        self.model = model
        self.base_url = base_url
        self.connection_name = connection_name
        self.host = host_of(base_url)
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
                if response.is_error:
                    await response.aread()
                    raise http_error(self.connection_name, response.status_code, response.text, None, self.model)
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    # A failure after the 200 arrives as an error line; the status can't change any more.
                    if "error" in data:
                        raise LLMError(f"{self.connection_name}: {data['error']}")
                    if content := data.get("message", {}).get("content"):
                        yield content
                    if data.get("done"):
                        return
        except httpx.ConnectError as exc:
            raise LLMUnavailable(f"Can't reach {self.host}") from exc
        except (httpx.HTTPError, ValueError) as exc:  # ValueError: a line that isn't JSON
            raise LLMError(f"{self.connection_name} request failed: {exc}") from exc


class OpenAICompatibleLLM:
    """`POST {base_url}/chat/completions` with `stream: true`: OpenAI, OpenRouter, Groq, Mistral, DeepSeek, Gemini's
    OpenAI endpoint, LM Studio, vLLM, llama.cpp. No SDK: chat needs one streamed completion."""

    def __init__(
        self, model: str, base_url: str, api_key: str | None, connection_name: str = "OpenAI-compatible", transport=None
    ):
        self.model = model
        self.base_url = base_url
        self.connection_name = connection_name
        self.host = host_of(base_url)
        self._api_key = api_key
        self._transport = transport  # tests pass httpx.MockTransport

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": True,
        }
        client = httpx.AsyncClient(
            base_url=self.base_url, headers=_bearer(self._api_key), timeout=OLLAMA_TIMEOUT, transport=self._transport
        )
        try:
            async with client, client.stream("POST", "/chat/completions", json=body) as response:
                if response.is_error:
                    await response.aread()
                    raise http_error(
                        self.connection_name, response.status_code, response.text, self._api_key, self.model
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):  # blank separators and `: keep-alive` comments
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        return
                    chunk = json.loads(data)
                    # A failure after the 200 (OpenRouter sends one when the upstream model fails mid-answer).
                    if "error" in chunk:
                        raise LLMError(f"{self.connection_name}: {provider_message(data, self._api_key)}")
                    for choice in chunk.get("choices") or []:
                        # Only answer text: reasoning models also stream `reasoning_content` deltas.
                        if content := (choice.get("delta") or {}).get("content"):
                            yield content
        except httpx.ConnectError as exc:
            raise LLMUnavailable(f"Can't reach {self.host}") from exc
        except (httpx.HTTPError, ValueError) as exc:  # ValueError: a data line that isn't JSON
            raise LLMError(f"{self.connection_name} request failed: {masked(str(exc), self._api_key)}") from exc


class AnthropicLLM:
    host = ANTHROPIC_HOST

    def __init__(self, model: str, api_key: str, connection_name: str = "Anthropic", http_client=None):
        self.model = model
        self.connection_name = connection_name
        self._api_key = api_key
        # http_client: tests pass an httpx2.AsyncClient with httpx2.MockTransport (SDK 1.x runs on httpx2).
        self._client = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=settings.anthropic_max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f"Can't reach {ANTHROPIC_HOST}") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise LLMUnavailable(f"Key rejected by {self.connection_name}") from exc
        except anthropic.NotFoundError as exc:
            raise LLMUnavailable(f"Model {self.model} isn't available on {self.connection_name}") from exc
        # The base class on purpose: an overload mid-stream arrives as APIStatusError with status 200.
        except anthropic.APIError as exc:
            raise LLMError(f"{self.connection_name}: {masked(str(exc), self._api_key)}") from exc
        # A transport drop mid-stream (not an SSE `error` event): the SDK only wraps errors from the
        # initial send, so a read failure during iteration surfaces as a raw httpx2 exception.
        except httpx2.HTTPError as exc:
            raise LLMError(f"{self.connection_name}: {masked(str(exc), self._api_key)}") from exc


FAKE_ANSWER = "Fake answer: the method is described here [C1]."
# Word by word, with the citation marker split across two tokens like a real model does.
FAKE_TOKENS = ["Fake ", "answer: ", "the ", "method ", "is ", "described ", "here ", "[C", "1]", "."]
# Given the workspace system prompt: cites a passage from each of two papers and a note, as the workspace chat
# end-to-end spec expects.
FAKE_WORKSPACE_ANSWER = "Fake workspace answer: both papers describe the method [C1][C2], as your note says [N1]."
FAKE_WORKSPACE_TOKENS = [
    "Fake ", "workspace ", "answer: ", "both ", "papers ", "describe ", "the ", "method ",
    "[C", "1]", "[C", "2]", ", ", "as ", "your ", "note ", "says ", "[N", "1]", ".",
]
# What every connection lists on the fake stack, and the key its Test connection rejects.
FAKE_MODELS = ["fake-large", "fake-small"]
FAKE_BAD_KEY = "bad-key"
# Between fake tokens on the E2E stack, so answers stream visibly instead of in one burst.
FAKE_DELAY = 0.05


class FakeLLM:
    """Deterministic, offline. LLM_PROVIDER=fake makes build_llm return it, so the E2E stack answers without a model."""

    host = "fake"

    def __init__(
        self, model: str = "fake", connection_name: str = "Fake", fail_after: int | None = None, delay: float = 0.0
    ):
        self.model = model
        self.connection_name = connection_name
        self.fail_after = fail_after  # raise LLMError after this many tokens
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((system, prompt))
        tokens = FAKE_WORKSPACE_TOKENS if system == WORKSPACE_SYSTEM_PROMPT else FAKE_TOKENS
        for index, token in enumerate(tokens):
            if index == self.fail_after:
                raise LLMError("fake model failed mid-answer")
            await asyncio.sleep(self.delay)
            yield token


def build_llm(connection, name: str, transport=None) -> LLM:
    """A new adapter for one question, from the connection's current values: an edit applies to the next question.

    ponytail: one SDK client per question; cache by (connection id, updated_at) only if that shows up in timings.
    """
    if settings.llm_provider == "fake":
        # `fake:` keeps a fake answer from ever being recorded as the real model's output.
        return FakeLLM(model=f"fake:{name}", connection_name=connection.label, delay=FAKE_DELAY)
    if connection.kind == "anthropic":
        return AnthropicLLM(name, connection.api_key, connection.label)
    if connection.kind == "ollama":
        return OllamaLLM(name, connection.base_url, connection.label, transport=transport)
    return OpenAICompatibleLLM(name, connection.base_url, connection.api_key, connection.label, transport=transport)


async def list_models(connection, transport=None, http_client=None) -> list[str] | None:
    """The provider's model names, sorted; None when the endpoint has no list (404), so names are typed by hand.

    Raises LLMUnavailable (key rejected, can't reach) or LLMError. `http_client` is Anthropic's httpx2 client in tests.
    """
    if settings.llm_provider == "fake":
        if connection.api_key == FAKE_BAD_KEY:
            raise LLMUnavailable(f"Key rejected by {connection.label}")
        return list(FAKE_MODELS)
    if connection.kind == "anthropic":
        return await _anthropic_models(connection, http_client)
    path, field, key = ("/api/tags", "models", "name") if connection.kind == "ollama" else ("/models", "data", "id")
    client = httpx.AsyncClient(
        base_url=connection.base_url, headers=_bearer(connection.api_key), timeout=LIST_TIMEOUT, transport=transport
    )
    try:
        async with client:
            response = await client.get(path)
    except httpx.ConnectError as exc:
        raise LLMUnavailable(f"Can't reach {host_of(connection.base_url)}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"{connection.label} request failed: {masked(str(exc), connection.api_key)}") from exc
    if response.status_code == 404:
        return None
    if response.is_error:
        raise http_error(connection.label, response.status_code, response.text, connection.api_key)
    try:
        return sorted(entry[key] for entry in response.json()[field])
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMError(f"{connection.label} sent a model list PaperLab can't read") from exc


async def _anthropic_models(connection, http_client) -> list[str] | None:
    # No retries: Test connection should answer at once, and the owner can press it again.
    client = anthropic.AsyncAnthropic(api_key=connection.api_key, http_client=http_client, max_retries=0)
    try:
        return sorted([model.id async for model in client.models.list()])
    except anthropic.NotFoundError:
        return None
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
        raise LLMUnavailable(f"Key rejected by {connection.label}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable(f"Can't reach {ANTHROPIC_HOST}") from exc
    except anthropic.APIStatusError as exc:
        message = provider_message(exc.response.text, connection.api_key)
        raise LLMError(f"{connection.label} returned {exc.status_code}: {message}") from exc


@functools.cache
def get_llm() -> LLM:
    """The configured provider, built once per process. Chat routes depend on it, so tests override it."""
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model, settings.anthropic_api_key)
    if settings.llm_provider == "fake":
        # A small delay so the E2E stack streams visibly instead of in one burst.
        return FakeLLM(delay=0.05)
    return OllamaLLM(settings.llm_model, settings.ollama_url)
