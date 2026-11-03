import pytest

from app.core.voice_latency import percentiles
from app.models.voice_turn import VoiceTurn

pytestmark = pytest.mark.anyio


def test_percentiles_appear_only_with_enough_turns():
    assert percentiles(list(range(9))).p90 is None
    assert percentiles(list(range(10))).p90 is not None and percentiles(list(range(10))).p95 is None
    assert percentiles(list(range(20))).p95 is not None and percentiles(list(range(20))).p99 is None
    assert percentiles(list(range(100))).p99 is not None


def test_no_turns_gives_n_zero_and_no_numbers():
    p = percentiles([])
    assert (p.n, p.median, p.p90, p.p95, p.p99) == (0, None, None, None, None)


def test_median_of_an_even_count_is_the_midpoint():
    assert percentiles([10, 20, 30, 40]).median == 25


def test_nearest_rank_percentiles():
    p = percentiles(list(range(1, 101)))
    assert (p.median, p.p90, p.p95, p.p99) == (50.5, 90, 95, 99)


def turn(**kw) -> VoiceTurn:
    return VoiceTurn(**{"model": "m", "cold": False, "whole_paper": False, **kw})


async def groups(client):
    response = await client.get("/api/voice/latency")
    assert response.status_code == 200
    return {g["model"]: g for g in response.json()["groups"]}


async def test_route_keeps_cold_and_warm_apart_and_groups_by_model(client, session):
    session.add_all(
        [
            turn(model="a", cold=True, stt_ms=900, total_ms=3000),
            turn(model="a", stt_ms=100, total_ms=1000),
            turn(model="a", stt_ms=300),  # a failed turn: no total, still counts for stt
            turn(model="b", stt_ms=50, total_ms=500),
        ]
    )
    await session.flush()

    got = await groups(client)

    assert got["a"]["cold"]["stt_ms"]["n"] == 1 and got["a"]["cold"]["stt_ms"]["median"] == 900
    assert got["a"]["warm"]["stt_ms"]["n"] == 2 and got["a"]["warm"]["stt_ms"]["median"] == 200
    assert got["a"]["warm"]["total_ms"]["n"] == 1
    assert got["a"]["warm"]["embed_ms"]["n"] == 0 and got["a"]["warm"]["embed_ms"]["median"] is None
    assert got["b"]["warm"]["stt_ms"]["n"] == 1 and got["b"]["cold"]["stt_ms"]["n"] == 0


async def test_route_leaves_out_a_turn_of_a_minute_or_more_as_a_sleeping_mac(client, session):
    session.add_all([turn(stt_ms=100, total_ms=1000), turn(stt_ms=999999, total_ms=60000, interrupted=True)])
    await session.flush()

    group = (await groups(client))["m"]

    assert group["warm"]["stt_ms"]["n"] == 1 and group["warm"]["stt_ms"]["median"] == 100
    assert group["interrupts"] == 0


async def test_route_counts_interruptions_and_the_false_ones(client, session):
    session.add_all(
        [
            turn(interrupted=True, false_interrupt=True),
            turn(interrupted=True),
            turn(interrupted=True),
            turn(),
        ]
    )
    await session.flush()

    group = (await groups(client))["m"]

    assert (group["interrupts"], group["false_interrupts"]) == (3, 1)


async def test_route_with_no_turns_has_no_groups(client):
    assert await groups(client) == {}
