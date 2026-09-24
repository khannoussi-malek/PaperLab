"""The search sources behind a model connection (D150–D155): Ollama, and OpenAI with OpenAI-compatible servers. Each is
an async TextEmbedder built per call by embedding.build from the connection's current values, like build_llm; under
LLM_PROVIDER=fake every one is FakeRemoteEmbedder.

`source` is anything with kind, model, name, label, is_local, host, base_url and api_key (embedding_sources.Source).
A call's batches go one after another, so at most ARQ's 10 jobs send requests at once. Each request retries 429s, 5xx
answers and dropped reads (D155). Messages name the label and host; a key is masked wherever an answer echoes it.
ponytail: no per-process limit on requests in flight; add a semaphore here if 429s show up in the worker's log.
"""

import asyncio
import hashlib

import httpx
import numpy as np

from app.providers.base import DIMENSIONS, LLMError, LLMUnavailable, ModelNotPulled
from app.providers.llm import OLLAMA_TIMEOUT, _bearer, http_error, masked

ATTEMPTS = 4
RETRIED = {429, 500, 502, 503, 504}
FIRST_WAIT = 1.0  # seconds, then 2, then 4
MAX_WAIT = 20.0  # one batch stays well inside ARQ's 300 s job timeout
GAVE_UP = "{label} is limiting requests (429), and PaperLab gave up after 4 tries. Try again in a few minutes."
_sleep = asyncio.sleep  # tests record the waits instead


def _wait(retry_after: str | None, attempt: int) -> float:
    """Retry-After's seconds when the answer gives them, else 1, 2, 4 s; never more than MAX_WAIT.
    ponytail: an HTTP-date Retry-After counts as none."""
    try:
        seconds = float(retry_after)
    except (TypeError, ValueError):
        seconds = FIRST_WAIT * 2 ** (attempt - 1)
    return min(seconds, MAX_WAIT)


async def _post(client: httpx.AsyncClient, url: str, body: dict, source) -> httpx.Response:
    """The last answer after D155's retries. A refused connection is LLMUnavailable at once (waiting won't start a
    server); reads that keep dropping are LLMError."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = await client.post(url, json=body)
        except httpx.ConnectError as exc:
            raise LLMUnavailable(f"Can't reach {source.host}") from exc
        except (httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            if attempt == ATTEMPTS:
                raise LLMError(f"{source.label} request failed: {masked(str(exc), source.api_key)}") from exc
            await _sleep(_wait(None, attempt))
            continue
        except httpx.HTTPError as exc:
            raise LLMError(f"{source.label} request failed: {masked(str(exc), source.api_key)}") from exc
        if response.status_code not in RETRIED or attempt == ATTEMPTS:
            return response
        await _sleep(_wait(response.headers.get("Retry-After"), attempt))
    raise AssertionError("unreachable: the last attempt returns or raises")


def _json(response: httpx.Response, source) -> dict:
    """A successful answer's body; a failed one in words (M9's http_error, the key masked)."""
    if response.status_code == 429:
        raise LLMError(GAVE_UP.format(label=source.label))
    if response.is_error:
        raise http_error(source.label, response.status_code, response.text, source.api_key, source.model)
    try:
        return response.json()
    except ValueError as exc:
        raise LLMError(f"{source.label} sent an answer PaperLab can't read") from exc


class _Remote:
    """What the HTTP sources share: the source's names and prefixes, and one client for all of a call's batches."""

    BATCH = 32

    def __init__(self, source, prefixes: tuple[str, str], transport=None):
        self.name, self.label, self.model, self.is_local = source.name, source.label, source.model, source.is_local
        self.document_prefix, self.query_prefix = prefixes
        self._source = source
        self._transport = transport  # tests pass httpx.MockTransport

    async def encode(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        headers = self._headers()
        async with httpx.AsyncClient(headers=headers, timeout=OLLAMA_TIMEOUT, transport=self._transport) as client:
            try:
                for start in range(0, len(texts), self.BATCH):
                    vectors += await self._batch(client, texts[start : start + self.BATCH])
            except (KeyError, TypeError, IndexError) as exc:  # an answer of another shape
                raise LLMError(f"{self.label} sent an answer PaperLab can't read") from exc
        return vectors

    def _headers(self) -> dict[str, str]:
        return {}

    async def _batch(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class OllamaEmbedder(_Remote):
    """POST {base_url}/api/embed with nomic-embed-text, 32 texts a request, truncated to its context (D152). A 404 is
    the model not pulled yet."""

    BATCH = 32

    async def _batch(self, client, texts):
        body = {"model": self.model, "input": texts, "truncate": True}
        response = await _post(client, f"{self._source.base_url}/api/embed", body, self._source)
        if response.status_code == 404:
            raise ModelNotPulled(f"{self.model} isn't in {self.label} yet")
        return _json(response, self._source)["embeddings"]


class OpenAIEmbedder(_Remote):
    """POST {base_url}/embeddings, 128 texts a request, vectors ordered by `index` (D153). OpenAI asks for 768
    dimensions. A compatible server gets none (vLLM refuses it for models not trained to shorten) and must give 768
    itself. ponytail: a compatible server that needs `dimensions` to reach 768 is refused by the funnel; add a "send
    dimensions" switch to the connection if someone needs one."""

    BATCH = 128

    def _headers(self):
        return _bearer(self._source.api_key)

    async def _batch(self, client, texts):
        body = {"model": self.model, "input": texts, "encoding_format": "float"}
        if self._source.kind == "openai":
            body["dimensions"] = DIMENSIONS
        response = await _post(client, f"{self._source.base_url}/embeddings", body, self._source)
        data = _json(response, self._source)["data"]
        return [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]


class FakeRemoteEmbedder:
    """LLM_PROVIDER=fake's stand-in for every connection-based source (M9 decision 13): DIMENSIONS numbers from a hash
    of each text, offline. It records under the source's own name, which embedding_sources.name_for makes `fake:…`."""

    def __init__(self, source, prefixes: tuple[str, str], transport=None):
        self.name, self.label, self.model, self.is_local = source.name, source.label, source.model, source.is_local
        self.document_prefix, self.query_prefix = prefixes

    async def encode(self, texts: list[str]) -> list[list[float]]:
        return [np.random.default_rng(_seed(text)).standard_normal(DIMENSIONS).tolist() for text in texts]


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


ADAPTERS = {"ollama": OllamaEmbedder, "openai": OpenAIEmbedder, "openai_compatible": OpenAIEmbedder}
