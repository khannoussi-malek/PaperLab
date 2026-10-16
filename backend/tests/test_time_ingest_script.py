import httpx
import pytest

from scripts import time_ingest


def fake_api(statuses: list[str], error: str | None = None):
    """An API whose paper walks through `statuses`, one per GET, then stays on the last."""
    seen = iter(statuses)
    last = {"status": statuses[0]}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/papers"
            assert b'name="file"' in request.content
            return httpx.Response(201, json={"id": "p1", "status": "uploaded"})
        last["status"] = next(seen, last["status"])
        return httpx.Response(200, json={"id": "p1", "status": last["status"], "status_error": error})

    return httpx.Client(transport=httpx.MockTransport(handle), base_url="http://stack")


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_each_stage_is_timed_from_its_first_sighting():
    clock = Clock()
    statuses = ["uploaded", "extracting", "extracting", "chunking", "embedding", "embedding", "embedding", "ready"]

    result = time_ingest.track(fake_api(statuses), "p1", timeout=100, clock=clock, sleep=clock.sleep)

    assert result.stages == {
        "uploaded": 0.0,
        "extracting": 2.0,
        "chunking": 6.0,
        "embedding": 8.0,
        "ready": 14.0,
    }
    assert (result.final, result.total, result.error) == ("ready", 14.0, None)


def test_a_failed_paper_reports_its_error():
    clock = Clock()

    result = time_ingest.track(
        fake_api(["extracting", "failed"], error="Boom"), "p1", timeout=100, clock=clock, sleep=clock.sleep
    )

    assert (result.final, result.error) == ("failed", "Boom")


def test_it_gives_up_at_the_timeout():
    clock = Clock()

    result = time_ingest.track(fake_api(["embedding"]), "p1", timeout=10, clock=clock, sleep=clock.sleep)

    assert (result.final, result.total) == ("embedding", 10.0)


def test_the_live_api_port_is_refused_without_the_flag():
    with pytest.raises(SystemExit):
        time_ingest.check_not_live("http://localhost:8000", allowed=False)
    time_ingest.check_not_live("http://localhost:8000", allowed=True)
    time_ingest.check_not_live("http://localhost:8100", allowed=False)


def test_an_api_without_a_scheme_is_still_checked():
    assert time_ingest.normalise_api("localhost:8100") == "http://localhost:8100"
    assert time_ingest.normalise_api("https://stack:1") == "https://stack:1"
    with pytest.raises(SystemExit):
        time_ingest.check_not_live(time_ingest.normalise_api("localhost:8000"), allowed=False)
