"""Transport wrappers shared across providers: retry-on-429 (today only Semantic Scholar's unauthenticated pool
needs it) and a minimum-interval pacer, either private to one client or shared across several (two different
providers hitting one externally rate-limited host, e.g. NCBI's eutils, shared by PubMed and PMC)."""

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


class _Pacer:
    """Shared timing state: waits at least `min_interval_seconds` since the LAST CALLER's turn (not this
    object's own creation) before letting the next one through. A lock makes this safe when two coroutines
    (e.g. two different provider clients' concurrent requests, fired by asyncio.gather) call it at once --
    without it, both could read "no wait needed" before either updates the shared clock.

    The lock is rebuilt whenever the running event loop changes (tracked via `_lock_loop`), not just built
    once in `__init__`: `shared_pacer` caches a `_Pacer` at module level, so the SAME instance outlives any
    one event loop (each independent `asyncio.run()` -- every pytest-anyio test gets its own -- starts a
    new loop). An `asyncio.Lock()` binds to whichever loop first awaits it; reusing one from a prior,
    already-finished loop raises "bound to a different event loop" instead of just working. Rebuilding on
    loop change keeps real within-one-loop concurrent callers (the actual case this lock protects:
    asyncio.gather over several sources) correctly serialized, while never handing a stale lock across a
    loop boundary (confirmed this was a real crash, not just slower tests: the full backend suite hit it
    via pytest-anyio's per-test event loops)."""

    def __init__(self, min_interval_seconds: float):
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at: float | None = None
        self._lock = asyncio.Lock()
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    async def wait_turn(self) -> None:
        loop = asyncio.get_running_loop()
        if loop is not self._lock_loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        async with self._lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                wait = self.min_interval_seconds - (now - self._last_request_at)
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.monotonic()
            self._last_request_at = now


_shared_pacers: dict[tuple[str, str | None], _Pacer] = {}


def shared_pacer(group: str, key: str | None, min_interval_seconds: float) -> _Pacer:
    """One _Pacer per (group, key), reused across every call -- for two or more httpx clients (different
    transports, different lifecycles) that must share one rate budget against a common externally-enforced
    limit, e.g. NCBI's eutils limit shared by PubMed and PMC, enforced per IP or per API key, not per httpx
    client."""
    cache_key = (group, key)
    if cache_key not in _shared_pacers:
        _shared_pacers[cache_key] = _Pacer(min_interval_seconds)
    return _shared_pacers[cache_key]


class RateLimited(httpx.AsyncBaseTransport):
    """Waits at least `min_interval_seconds` since the pacer's last request before sending the next one.
    By default (`pacer` omitted) builds a private pacer from `min_interval_seconds` -- today's behavior,
    for a source with no cross-client sharing need. Pass a pre-built `_Pacer` via `pacer=` instead (from
    `shared_pacer`) to share one rate budget across multiple clients that hit the same externally-limited
    host."""

    def __init__(
        self, inner: httpx.AsyncBaseTransport, min_interval_seconds: float = 0.0, *, pacer: _Pacer | None = None
    ):
        self.inner = inner
        self._pacer = pacer if pacer is not None else _Pacer(min_interval_seconds)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self._pacer.wait_turn()
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()
