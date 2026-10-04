"""Transport wrappers shared across providers: retry-on-429 (today only Semantic Scholar's unauthenticated pool
needs it) and a minimum-interval pacer (not yet used by any of today's 5 sources; a future source with a
documented per-second limit — e.g. arXiv's own 3-second rule — could wire this in by extending its registry
entry (app/core/source_registry.py's SourceSpec) to carry one)."""

import asyncio
import time

import httpx


class RetryOn429(httpx.AsyncBaseTransport):
    """Retries a 429 response once per entry in `delays`, waiting that long first. Still 429 after every delay is
    spent: returns that last response as-is (the caller's `raise_for_status()` turns it into an error)."""

    def __init__(self, inner: httpx.AsyncBaseTransport, delays: tuple[float, ...]):
        self.inner = inner
        self.delays = delays

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        for delay in self.delays:
            response = await self.inner.handle_async_request(request)
            if response.status_code != 429:
                return response
            await response.aclose()
            await asyncio.sleep(delay)
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


class RateLimited(httpx.AsyncBaseTransport):
    """Waits at least `min_interval_seconds` since this transport's last request before sending the next one.
    Reads the clock exactly once per request, and measures the next wait from that reading (not from when any
    sleep actually finished) — a small, deliberate simplification (ponytail: paces from scheduled time, not
    actual-send time; a sub-millisecond drift under real load is not worth a second clock read to avoid)."""

    def __init__(self, inner: httpx.AsyncBaseTransport, min_interval_seconds: float):
        self.inner = inner
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at: float | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        now = time.monotonic()
        if self._last_request_at is not None:
            wait = self.min_interval_seconds - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_request_at = now
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()
