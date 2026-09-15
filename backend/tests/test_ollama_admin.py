import json

import httpx
import pytest

from app.config import settings
from app.providers import ollama_admin
from app.providers.base import LLMError, LLMUnavailable

pytestmark = pytest.mark.anyio

OLLAMA_URL = "http://ollama.test:11434"


def ndjson(*lines: dict) -> str:
    return "".join(json.dumps(line) + "\n" for line in lines)


async def pulled(handler, name="qwen3:8b") -> list[dict]:
    return [line async for line in ollama_admin.pull(OLLAMA_URL, name, transport=httpx.MockTransport(handler))]


async def test_pull_yields_progress_lines_in_order_until_success():
    requests = []
    lines = [
        {"status": "pulling manifest"},
        {"status": "pulling a1b2", "digest": "sha256:a1b2", "total": 100, "completed": 40},
        {"status": "pulling a1b2", "digest": "sha256:a1b2", "total": 100, "completed": 100},
        {"status": "success"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=ndjson(*lines), headers={"content-type": "application/x-ndjson"})

    assert await pulled(handler, "hf.co/org/model:Q4_K_M") == lines
    assert (requests[0].method, str(requests[0].url)) == ("POST", f"{OLLAMA_URL}/api/pull")
    assert json.loads(requests[0].content) == {"model": "hf.co/org/model:Q4_K_M", "stream": True}


async def test_pull_error_line_mid_stream_is_an_llm_error_after_the_lines_before_it():
    # What Ollama 0.14 answers for a name it can't find: a 200, then an error line.
    body = ndjson({"status": "pulling manifest"}, {"error": "pull model manifest: file does not exist"})
    seen = []

    with pytest.raises(LLMError, match="^Ollama: pull model manifest: file does not exist$"):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        async for line in ollama_admin.pull(OLLAMA_URL, "nope", transport=transport):
            seen.append(line)
    assert seen == [{"status": "pulling manifest"}]


@pytest.mark.parametrize(
    ("handler", "error", "message"),
    [
        (lambda r: httpx.Response(500, json={"error": "disk full"}), LLMError, "^Ollama returned 500: disk full$"),
        (lambda r: httpx.Response(200, text=ndjson({"status": "pulling manifest"})), LLMError, "stopped before it"),
        (lambda r: httpx.Response(200, text="not json\n"), LLMError, "^Ollama request failed: "),
    ],
)
async def test_pull_failures_are_llm_errors(handler, error, message):
    with pytest.raises(error, match=message):
        await pulled(handler)


async def test_pull_when_ollama_is_not_running_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMUnavailable, match="^Can't reach ollama.test$"):
        await pulled(handler)


async def test_delete_removes_the_model_or_says_it_was_not_installed():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        name = json.loads(request.content)["model"]
        if name != "qwen3:8b":
            return httpx.Response(404, json={"error": f"model '{name}' not found"})
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    assert await ollama_admin.delete(OLLAMA_URL, "qwen3:8b", transport=transport) is True
    assert await ollama_admin.delete(OLLAMA_URL, "missing:latest", transport=transport) is False
    assert (requests[0].method, str(requests[0].url)) == ("DELETE", f"{OLLAMA_URL}/api/delete")


async def test_delete_failures():
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMUnavailable, match="^Can't reach ollama.test$"):
        await ollama_admin.delete(OLLAMA_URL, "qwen3:8b", transport=httpx.MockTransport(refused))
    broken = httpx.MockTransport(lambda r: httpx.Response(500, json={"error": "busy"}))
    with pytest.raises(LLMError, match="^Ollama returned 500: busy$"):
        await ollama_admin.delete(OLLAMA_URL, "qwen3:8b", transport=broken)


async def test_fake_mode_scripts_a_pull_and_a_delete_without_the_network(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(ollama_admin, "FAKE_PULL_DELAY", 0)

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("fake mode must not call Ollama")

    lines = await pulled(no_network)
    assert [line.get("completed") for line in lines if "total" in line] == [20, 40, 60, 80, 100]
    assert lines[-1] == {"status": "success"}
    assert await ollama_admin.delete(OLLAMA_URL, "anything", transport=httpx.MockTransport(no_network)) is True
