"""Transport wrappers shared across providers: retry-on-429 (today only Semantic Scholar's unauthenticated pool
needs it) and a minimum-interval pacer: private to one client, shared across a process's clients (two providers
hitting one externally rate-limited host, e.g. NCBI's eutils, shared by PubMed and PMC), or shared across every run
and process through Redis (SharedPacer)."""

import asyncio
import logging
import time
from typing import Any

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)


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
        self, inner: httpx.AsyncBaseTransport, min_interval_seconds: float = 0.0, *,
        pacer: "_Pacer | SharedPacer | None" = None,
    ):
        self.inner = inner
        self._pacer = pacer if pacer is not None else _Pacer(min_interval_seconds)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self._pacer.wait_turn()
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


class SharedPacer:
    """A rate budget shared by every run, worker and process, kept in Redis. Time is cut into slots one interval long.
    A caller claims the next free slot with SET NX, then sleeps until it starts, so two requests are never closer than
    one interval however many runs are asking. Redis trouble falls back to `local`, one process's pacer: a busy Redis
    must not stop a search, and the worst case is the old behaviour.

    ponytail: slots come from the caller's clock, so this assumes one machine's containers; fleets need Redis TIME.
    """

    MAX_SLOTS_AHEAD = 1000  # far past any real queue: a run asks one page at a time

    def __init__(self, group: str, min_interval_seconds: float, redis: Any = None):
        self.group = group
        self.interval = min_interval_seconds
        self._redis = redis
        self._local = _Pacer(min_interval_seconds)

    def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        return _redis_for_this_loop()

    async def wait_turn(self) -> None:
        try:
            client = self._client()
            interval_ms = int(self.interval * 1000)
            now_ms = int(time.time() * 1000)
            first = now_ms // interval_ms + 1
            for slot in range(first, first + self.MAX_SLOTS_AHEAD):
                starts_in_ms = slot * interval_ms - now_ms
                # The key lasts past its slot's start, so nobody can claim a slot still waiting to run.
                claimed = await client.set(
                    f"paperlab:pace:{self.group}:{slot}", 1, nx=True, px=starts_in_ms + interval_ms * 2
                )
                if claimed:
                    await asyncio.sleep(max(slot * interval_ms / 1000 - time.time(), 0))
                    return
        except (RedisError, OSError) as exc:
            logger.warning("rate limit for %s fell back to this process: %s", self.group, exc)
        await self._local.wait_turn()


_redis_clients: dict[asyncio.AbstractEventLoop, Any] = {}


def _redis_for_this_loop() -> Any:
    """A connection belongs to one event loop; a process normally has one."""
    loop = asyncio.get_running_loop()
    if loop not in _redis_clients:
        _redis_clients.clear()  # a finished loop's connections are no use to anyone
        _redis_clients[loop] = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
    return _redis_clients[loop]


# What each host asks for, per request. Crossref's budget covers ACM too, which is served from Crossref.
SOURCE_INTERVAL_SECONDS = {"arxiv": 3.0, "crossref": 1.0, "semantic_scholar": 1.0}
_shared_source_pacers: dict[str, SharedPacer] = {}


def paced(group: str, inner: httpx.AsyncBaseTransport) -> httpx.AsyncBaseTransport:
    """`inner` behind `group`'s budget across every run and process (SOURCE_INTERVAL_SECONDS)."""
    pacer = _shared_source_pacers.setdefault(group, SharedPacer(group, SOURCE_INTERVAL_SECONDS[group]))
    return RateLimited(inner, pacer=pacer)


CONNECT_RETRIES = 2


def retrying(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncBaseTransport:
    """A test's transport as given; else a real one that retries a failed connection (DNS, refused). Docker's DNS in
    the worker fails a lookup now and then, and one blip left uploads without authors or year. httpx retries only
    connection errors, never a request that reached the server."""
    return transport or httpx.AsyncHTTPTransport(retries=CONNECT_RETRIES)
