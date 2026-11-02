"""Six search runs at once must not exceed a source's rate, whichever process each runs in."""

import asyncio
import time

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.providers import arxiv, crossref, semantic_scholar
from app.providers.http import RateLimited, SharedPacer, _Pacer

pytestmark = pytest.mark.anyio

INTERVAL = 0.05
# asyncio.sleep can't wake early by much, but two wake-ups on one tick record a hair apart.
TOLERANCE = 0.005
ATOM = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'


class FakeRedis:
    """Redis's SET NX PX, which is all the pacer needs."""

    def __init__(self):
        self.keys: dict[str, float] = {}

    async def set(self, key: str, value: int, *, nx: bool, px: int) -> bool:
        await asyncio.sleep(0)  # a real round trip gives other runs a turn
        now = time.monotonic()
        if nx and self.keys.get(key, 0) > now:
            return False
        self.keys[key] = now + px / 1000
        return True


def recording_transport(times: list[float]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        times.append(time.monotonic())
        return httpx.Response(200, text=ATOM)

    return httpx.MockTransport(handler)


async def six_runs(pacer_for_run) -> list[float]:
    """Six runs page three times each through arXiv's real paging code."""
    times: list[float] = []

    async def run(number: int) -> None:
        transport = RateLimited(recording_transport(times), pacer=pacer_for_run(number))
        async with arxiv.new_client(transport=transport) as http:
            for page in range(3):
                await arxiv.search_page(http, "software design creativity", 20, page * 20)

    await asyncio.gather(*(run(number) for number in range(6)))
    return sorted(times)


def closest_gap(times: list[float]) -> float:
    return min(later - earlier for earlier, later in zip(times, times[1:]))


async def test_six_parallel_runs_in_different_workers_never_exceed_the_rate():
    redis = FakeRedis()
    # Each run gets its own pacer, as a run in another worker process would: only Redis is shared.
    times = await six_runs(lambda _run: SharedPacer("arxiv", INTERVAL, redis=redis))
    assert len(times) == 18
    assert closest_gap(times) >= INTERVAL - TOLERANCE


async def test_a_pacer_per_run_is_what_let_them_exceed_it():
    times = await six_runs(lambda _run: _Pacer(INTERVAL))
    assert closest_gap(times) < INTERVAL / 2  # the test above can fail


async def test_a_claimed_slot_is_not_claimed_again_while_it_waits_to_run():
    redis = FakeRedis()
    pacer = SharedPacer("arxiv", INTERVAL, redis=redis)
    times: list[float] = []

    async def one() -> None:
        await pacer.wait_turn()
        times.append(time.monotonic())

    # A queue longer than a slot's own key would last if it were set for a fixed time.
    await asyncio.gather(*(one() for _ in range(12)))
    await one()
    assert closest_gap(sorted(times)) >= INTERVAL - TOLERANCE


async def test_a_redis_outage_falls_back_to_this_process_and_never_stops_a_search(caplog):
    class DownRedis:
        async def set(self, *_args, **_kwargs):
            raise RedisConnectionError("no route")

    pacer = SharedPacer("arxiv", INTERVAL, redis=DownRedis())
    times: list[float] = []

    async def one() -> None:
        await pacer.wait_turn()
        times.append(time.monotonic())

    await asyncio.gather(*(one() for _ in range(4)))
    assert len(times) == 4 and closest_gap(sorted(times)) >= INTERVAL - TOLERANCE
    assert "fell back" in caplog.text


@pytest.mark.parametrize(("provider", "group"), [(arxiv, "arxiv"), (crossref, "crossref")])
async def test_a_real_client_uses_its_sources_shared_budget(provider, group):
    async with provider.new_client() as http:
        assert http._transport._pacer.group == group


async def test_semantic_scholars_retries_stay_inside_its_budget():
    async with semantic_scholar.new_client() as http:
        assert http._transport.inner._pacer.group == "semantic_scholar"
    async with semantic_scholar.new_client(retry_429=False) as http:
        assert http._transport._pacer.group == "semantic_scholar"
