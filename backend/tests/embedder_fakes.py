"""The embedding APIs of Ollama and OpenAI (and OpenAI-compatible servers) behind one httpx.MockTransport, for the
search source tests (D159). No network: every request is answered here and recorded."""

import json
import math
import random
from types import SimpleNamespace

import httpx

KEY = "sk-test-EMBED9876"
OPENAI_URL = "https://api.openai.com/v1"
OLLAMA_URL = "http://ollama.test:11434"
COMPAT_URL = "http://vllm.test:8000/v1"
# What a model gives when nothing shortens it: OpenAI's text-embedding-3 sizes.
NATIVE = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}
# Predicted from Ollama's chat endpoint, which answers a missing model this way (spec D152).
NOT_PULLED = {"error": 'model "nomic-embed-text" not found, try pulling it first'}
SOURCES = {
    "ollama": dict(
        model="nomic-embed-text", base_url=OLLAMA_URL, api_key=None, label="Ollama", host="ollama.test",
        name="ollama/nomic-embed-text",
    ),
    "openai": dict(
        model="text-embedding-3-small", base_url=OPENAI_URL, api_key=KEY, label="OpenAI", host="api.openai.com",
        name="openai/text-embedding-3-small@768",
    ),
    "openai_compatible": dict(
        model="bge-m3", base_url=COMPAT_URL, api_key=KEY, label="vLLM", host="vllm.test",
        name="compat/vllm.test:8000/bge-m3",
    ),
}  # fmt: skip


def vector(text: str, size: int) -> list[float]:
    """`size` numbers seeded by the text, at length 2: the funnel has to normalise them."""
    rng = random.Random(text)
    numbers = [rng.gauss(0, 1) for _ in range(size)]
    norm = math.sqrt(sum(x * x for x in numbers))
    return [2 * x / norm for x in numbers]


def source(kind: str, **fields) -> SimpleNamespace:
    """What embedding.build reads from a search source (core/embedding_sources.Source), on a kind's usual connection."""
    return SimpleNamespace(kind=kind, is_local=False, **{**SOURCES[kind], **fields})


class FakeEmbeddings:
    """Routes by path: `/api/embed` (Ollama) and `/embeddings` (OpenAI and compatible servers).

    - `statuses` are answered first, one per request, in order: an HTTP status, "refuse" (ConnectError, like a server
      that isn't running) or "drop" (ReadTimeout). A 429 carries `Retry-After: 2`. An error body echoes the key the
      request sent, as some providers do.
    - `dims` is every vector's size, for a model that gives the wrong number. Otherwise OpenAI's models give
      `dimensions` when asked and their native size when not, and everything else gives 768.
    - `not_pulled` makes Ollama answer 404 as for a model it doesn't have.
    OpenAI's `data` comes back in reverse `index` order, so an adapter must sort it.
    """

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.statuses: list[int | str] = []
        self.dims: int | None = None
        self.not_pulled = False
        self.transport = httpx.MockTransport(self._handle)

    def bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.requests]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.statuses:
            return self._failure(request, self.statuses.pop(0))
        body = json.loads(request.content)
        path = request.url.path
        if path.endswith("/api/embed"):
            if self.not_pulled:
                return httpx.Response(404, json=NOT_PULLED)
            return httpx.Response(200, json={"embeddings": [vector(t, self.dims or 768) for t in body["input"]]})
        if path.endswith("/embeddings"):
            size = self.dims or body.get("dimensions") or NATIVE.get(body["model"], 768)
            data = [{"index": i, "embedding": vector(t, size)} for i, t in enumerate(body["input"])]
            return httpx.Response(200, json={"data": data[::-1], "usage": {"prompt_tokens": len(data)}})
        raise AssertionError(f"unrouted embedding request: {request.method} {request.url}")

    @staticmethod
    def _failure(request: httpx.Request, status: int | str) -> httpx.Response:
        if status == "refuse":
            raise httpx.ConnectError("connection refused", request=request)
        if status == "drop":
            raise httpx.ReadTimeout("timed out", request=request)
        key = request.headers.get("authorization", "").removeprefix("Bearer ") or request.headers.get("x-goog-api-key")
        headers = {"Retry-After": "2"} if status == 429 else {}
        body = {"error": {"message": f"Incorrect API key provided: {key}"}}
        return httpx.Response(status, headers=headers, json=body)
