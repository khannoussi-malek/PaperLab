import json

import httpx
import httpx2
import pytest

from app.config import settings
from app.providers import llm
from app.providers.base import LLMError, LLMUnavailable

pytestmark = pytest.mark.anyio

OLLAMA_URL = "http://ollama.test:11434"


async def collect(model, tokens: list[str]) -> list[str]:
    async for token in model.stream("You cite sources.", "Question: why?"):
        tokens.append(token)
    return tokens


def ndjson(*lines: dict) -> str:
    return "".join(json.dumps(line) + "\n" for line in lines)


def token_line(text: str) -> dict:
    return {"model": "qwen3:8b", "message": {"role": "assistant", "content": text}, "done": False}


def ollama(handler) -> llm.OllamaLLM:
    return llm.OllamaLLM("qwen3:8b", OLLAMA_URL, transport=httpx.MockTransport(handler))


async def test_ollama_streams_content_until_the_done_line():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = ndjson(
            token_line(""),  # thinking models can send empty content first
            token_line("Attention [C"),
            token_line("1]."),
            {"model": "qwen3:8b", "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
        )
        return httpx.Response(200, text=body, headers={"content-type": "application/x-ndjson"})

    assert await collect(ollama(handler), []) == ["Attention [C", "1]."]
    assert str(requests[0].url) == f"{OLLAMA_URL}/api/chat"
    assert json.loads(requests[0].content) == {
        "model": "qwen3:8b",
        "messages": [
            {"role": "system", "content": "You cite sources."},
            {"role": "user", "content": "Question: why?"},
        ],
        "stream": True,
        "think": False,
        "options": {"num_ctx": llm.OLLAMA_NUM_CTX},
    }


async def test_ollama_missing_model_is_unavailable():
    model = ollama(lambda request: httpx.Response(404, json={"error": "model 'qwen3:8b' not found"}))

    with pytest.raises(LLMUnavailable, match=r"^Model qwen3:8b isn't installed \(ollama pull qwen3:8b\)$"):
        await collect(model, [])


async def test_ollama_connection_refused_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMUnavailable, match=f"^Can't reach Ollama at {OLLAMA_URL}$"):
        await collect(ollama(handler), [])


def test_ollama_uses_a_generous_read_timeout_for_cold_model_loads():
    assert llm.OLLAMA_TIMEOUT == httpx.Timeout(120, connect=5)


async def test_ollama_error_line_mid_stream_is_an_llm_error():
    body = ndjson(token_line("Attention"), {"error": "an error was encountered while running the model"})
    model = ollama(lambda request: httpx.Response(200, text=body))
    tokens = []

    with pytest.raises(LLMError, match="an error was encountered while running the model"):
        await collect(model, tokens)
    assert tokens == ["Attention"]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def anthropic_body(texts: list[str], error: dict | None = None) -> str:
    message = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0},
    }
    body = sse("message_start", {"type": "message_start", "message": message})
    body += sse("content_block_start", {"type": "content_block_start", "index": 0,
                                        "content_block": {"type": "text", "text": ""}})
    for text in texts:
        body += sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                            "delta": {"type": "text_delta", "text": text}})
    if error:
        return body + sse("error", {"type": "error", "error": error})
    body += sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    body += sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                  "usage": {"output_tokens": 5}})
    return body + sse("message_stop", {"type": "message_stop"})


def anthropic_model(handler) -> llm.AnthropicLLM:
    # The anthropic SDK 1.x runs on httpx2, so its fake transport comes from httpx2 too.
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return llm.AnthropicLLM("claude-sonnet-5", "sk-test", http_client=client)


async def test_anthropic_streams_text():
    requests = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(json.loads(request.content))
        return httpx2.Response(200, text=anthropic_body(["Attention [C", "1]."]),
                               headers={"content-type": "text/event-stream"})

    assert await collect(anthropic_model(handler), []) == ["Attention [C", "1]."]
    assert requests[0]["system"] == "You cite sources."
    assert requests[0]["messages"] == [{"role": "user", "content": "Question: why?"}]
    assert (requests[0]["model"], requests[0]["stream"]) == ("claude-sonnet-5", True)


async def test_anthropic_overload_mid_stream_is_an_llm_error():
    overloaded = {"type": "overloaded_error", "message": "Overloaded"}

    def handler(request: httpx2.Request) -> httpx2.Response:
        # Arrives inside a 200 stream, so the SDK raises the generic APIStatusError, not OverloadedError.
        return httpx2.Response(200, text=anthropic_body(["Attention [C"], error=overloaded),
                               headers={"content-type": "text/event-stream"})

    tokens = []
    with pytest.raises(LLMError, match="Overloaded"):
        await collect(anthropic_model(handler), tokens)
    assert tokens == ["Attention [C"]


class _DropAfterOneChunk(httpx2.AsyncByteStream):
    """A transport that delivers some bytes, then dies — not an SSE `error` event."""

    def __init__(self, chunk: bytes):
        self._chunk = chunk

    async def __aiter__(self):
        yield self._chunk
        raise httpx2.ReadError("connection dropped")


async def test_anthropic_transport_error_mid_stream_is_an_llm_error():
    message = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0},
    }
    chunk = (
        sse("message_start", {"type": "message_start", "message": message})
        + sse("content_block_start", {"type": "content_block_start", "index": 0,
                                      "content_block": {"type": "text", "text": ""}})
        + sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                      "delta": {"type": "text_delta", "text": "Attention"}})
    ).encode()

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               stream=_DropAfterOneChunk(chunk))

    tokens = []
    with pytest.raises(LLMError, match="connection dropped"):
        await collect(anthropic_model(handler), tokens)
    assert tokens == ["Attention"]


async def test_anthropic_unknown_model_is_unavailable():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"type": "error", "error": {"type": "not_found_error", "message": "model"}})

    with pytest.raises(LLMUnavailable, match="^Model claude-sonnet-5 isn't available on the Anthropic API$"):
        await collect(anthropic_model(handler), [])


async def test_fake_llm_splits_the_citation_marker_and_records_calls():
    fake = llm.FakeLLM()

    tokens = await collect(fake, [])

    assert "".join(tokens) == llm.FAKE_ANSWER
    assert ["[C", "1]"] == tokens[tokens.index("[C") : tokens.index("[C") + 2]
    assert fake.calls == [("You cite sources.", "Question: why?")]


async def test_fake_llm_can_fail_mid_stream():
    tokens = []

    with pytest.raises(LLMError, match="fake model failed mid-answer"):
        await collect(llm.FakeLLM(fail_after=2), tokens)
    assert len(tokens) == 2


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("ollama", llm.OllamaLLM), ("anthropic", llm.AnthropicLLM), ("fake", llm.FakeLLM)],
)
def test_get_llm_builds_the_configured_provider_once(monkeypatch, provider, expected):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    llm.get_llm.cache_clear()
    try:
        assert isinstance(llm.get_llm(), expected)
        assert llm.get_llm() is llm.get_llm()
    finally:
        llm.get_llm.cache_clear()
