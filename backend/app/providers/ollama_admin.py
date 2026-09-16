"""Ollama's own model management, proxied: pull a model with progress, delete one. No Docker socket."""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.providers.base import LLMError, LLMUnavailable
from app.providers.llm import LIST_TIMEOUT, host_of, provider_message

# Verifying a multi-gigabyte layer can go minutes without a progress line.
PULL_TIMEOUT = httpx.Timeout(600, connect=5)
# The fake stack's pull: slow enough for the progress bar to be seen moving.
FAKE_PULL = [
    {"status": "pulling manifest"},
    *({"status": "downloading", "total": 100, "completed": done} for done in (20, 40, 60, 80, 100)),
    {"status": "verifying sha256 digest"},
    {"status": "success"},
]
FAKE_PULL_DELAY = 0.3


async def pull(base_url: str, name: str, transport=None) -> AsyncIterator[dict]:
    """Ollama's progress lines (`status`, and `total`/`completed` while downloading), ending with status "success".

    Raises LLMUnavailable when Ollama can't be reached, LLMError for an error status or an error line: an unknown name
    comes back as a 200 whose second line is `{"error": "pull model manifest: file does not exist"}`.
    """
    if settings.llm_provider == "fake":
        for line in FAKE_PULL:
            await asyncio.sleep(FAKE_PULL_DELAY)
            yield line
        return
    client = httpx.AsyncClient(base_url=base_url, timeout=PULL_TIMEOUT, transport=transport)
    try:
        async with client, client.stream("POST", "/api/pull", json={"model": name, "stream": True}) as response:
            if response.is_error:
                await response.aread()
                raise LLMError(f"Ollama returned {response.status_code}: {provider_message(response.text)}")
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise LLMError(f"Ollama: {data['error']}")
                yield data
                if data.get("status") == "success":
                    return
        raise LLMError(f"The download of {name} stopped before it finished")
    except httpx.ConnectError as exc:
        raise LLMUnavailable(f"Can't reach {host_of(base_url)}") from exc
    except (httpx.HTTPError, ValueError) as exc:  # ValueError: a line that isn't JSON
        raise LLMError(f"Ollama request failed: {exc}") from exc


async def delete(base_url: str, name: str, transport=None) -> bool:
    """Deletes a model from Ollama's disk. False when it isn't installed (404). Raises LLMUnavailable or LLMError."""
    if settings.llm_provider == "fake":
        return True
    client = httpx.AsyncClient(base_url=base_url, timeout=LIST_TIMEOUT, transport=transport)
    try:
        async with client:
            response = await client.request("DELETE", "/api/delete", json={"model": name})
    except httpx.ConnectError as exc:
        raise LLMUnavailable(f"Can't reach {host_of(base_url)}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc
    if response.status_code == 404:
        return False
    if response.is_error:
        raise LLMError(f"Ollama returned {response.status_code}: {provider_message(response.text)}")
    return True
