import asyncio
import time

import httpx
import pytest

from app.providers.http import RateLimited, RetryOn429

pytestmark = pytest.mark.anyio


async def test_retry_on_429_retries_then_succeeds():
    # Real delays, zeroed: this project's own convention for exercising a retry loop without a slow test (see
    # test_semantic_scholar.py's monkeypatch.setattr(semantic_scholar, "RETRY_DELAYS", (0, 0))) — mocking
    # asyncio.sleep itself is avoided, since a non-async replacement breaks `await asyncio.sleep(...)`.
    answers = iter([httpx.Response(429), httpx.Response(429), httpx.Response(200)])
    inner = httpx.MockTransport(lambda request: next(answers))
    wrapped = RetryOn429(inner, delays=(0.0, 0.0))

    response = await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))

    assert response.status_code == 200


async def test_retry_on_429_gives_up_after_every_delay_is_spent():
    calls = []
    inner = httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(429))
    wrapped = RetryOn429(inner, delays=(0.0, 0.0))

    response = await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))

    assert response.status_code == 429
    assert len(calls) == 3  # the first try plus one retry per delay


async def test_retry_on_429_does_not_retry_a_non_429_response():
    inner = httpx.MockTransport(lambda request: httpx.Response(500))
    wrapped = RetryOn429(inner, delays=(10.0,))  # a real 10s sleep would prove this test wrong if it ever ran

    response = await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))

    assert response.status_code == 500


async def test_rate_limited_waits_at_least_the_minimum_interval_between_requests(monkeypatch):
    clock = iter([0.0, 0.1])  # first request at t=0, second at t=0.1 (too soon) — one monotonic() read per request
    monkeypatch.setattr(time, "monotonic", lambda: next(clock, 0.1))
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)  # an async replacement: a plain lambda isn't awaitable
    inner = httpx.MockTransport(lambda request: httpx.Response(200))
    wrapped = RateLimited(inner, min_interval_seconds=0.5)

    await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))
    await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))

    assert sleeps == [0.4]  # 0.5 - (0.1 - 0.0)


async def test_rate_limited_does_not_wait_when_enough_time_already_passed(monkeypatch):
    clock = iter([0.0, 1.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock, 1.0))
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    inner = httpx.MockTransport(lambda request: httpx.Response(200))
    wrapped = RateLimited(inner, min_interval_seconds=0.5)

    await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))
    await wrapped.handle_async_request(httpx.Request("GET", "https://example.test"))

    assert sleeps == []
