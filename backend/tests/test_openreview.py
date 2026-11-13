from collections import deque

import httpx
import pytest

from app.core.candidates import from_openreview
from app.providers import openreview

pytestmark = pytest.mark.anyio

SUBMISSION = "ICLR.cc/2027/Conference/-/Submission"


def _note(**overrides):
    """An API v2 note: every content value wrapped in {"value": ...}, as the live endpoint answers."""
    note = {
        "id": "n1",
        "forum": "AbC123xyz",
        "cdate": 1_735_689_600_000,  # 2025-01-01T00:00:00Z
        "invitations": [SUBMISSION],
        "content": {
            "title": {"value": "Graph Neural Networks for Tabular Data"},
            "abstract": {"value": "We study <i>graph</i> models."},
            "authors": {"value": ["Ada Lovelace", "Alan Turing"]},
            "venue": {"value": "ICLR 2027 Submission"},
            "venueid": {"value": "ICLR.cc/2027/Conference"},
            "pdf": {"value": "/pdf/0123abcd.pdf"},
            "keywords": {"value": ["graphs"]},
        },
    }
    note.update(overrides)
    return note


def _scripted(*responses: httpx.Response):
    """A transport that answers each request with the next scripted response, recording every request."""
    queue, seen = deque(responses), []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.popleft()

    return httpx.MockTransport(handle), seen


@pytest.fixture(autouse=True)
def fresh_budget_and_no_sleeps(monkeypatch):
    """The token bucket is module-level, so every test starts with an empty one; waits are recorded, not slept."""
    openreview._sent_at.clear()
    sleeps: list[float] = []

    async def fake_wait(seconds: float) -> None:
        sleeps.append(seconds)
        openreview._sent_at.clear()  # a wait always outlasts the window, so the bucket empties too

    monkeypatch.setattr(openreview, "_wait", fake_wait)
    yield sleeps
    openreview._sent_at.clear()


# --- mapper -----------------------------------------------------------------------------------------------


def test_mapper_reads_title_abstract_authors_year_pdf_and_venue_from_api_v2_values():
    candidate = from_openreview(_note())

    assert candidate.title == "Graph Neural Networks for Tabular Data"
    assert candidate.authors == ["Ada Lovelace", "Alan Turing"]
    assert candidate.year == 2025
    assert candidate.venue == "ICLR 2027 Submission"
    assert candidate.abstract == "We study graph models."  # markup stripped, as the other mappers do
    assert candidate.pdf_urls == ["https://openreview.net/pdf/0123abcd.pdf"]
    assert candidate.external_ids == {"openreview": "AbC123xyz"}
    assert candidate.doi is None
    assert candidate.sources == ("openreview",)


def test_mapper_accepts_plain_string_content_values_too():
    note = _note(
        content={
            "title": "Plain Title",
            "abstract": "Plain abstract.",
            "authors": ["Grace Hopper"],
            "pdf": "http://arxiv.org/pdf/2401.00001v1",
        }
    )

    candidate = from_openreview(note)

    assert (candidate.title, candidate.abstract, candidate.authors) == (
        "Plain Title",
        "Plain abstract.",
        ["Grace Hopper"],
    )
    assert candidate.pdf_urls == ["http://arxiv.org/pdf/2401.00001v1"]  # an absolute link stays as it is


def test_a_blind_submission_with_no_authors_has_an_empty_author_list():
    note = _note(invitations=["ICLR.cc/2027/Conference/-/Blind_Submission"])
    del note["content"]["authors"]

    candidate = from_openreview(note)

    assert candidate is not None
    assert candidate.authors == []


def test_a_note_with_no_abstract_has_none():
    note = _note()
    del note["content"]["abstract"]

    assert from_openreview(note).abstract is None


def test_a_note_with_no_pdf_has_no_pdf_url():
    note = _note()
    del note["content"]["pdf"]

    assert from_openreview(note).pdf_urls == []


def test_a_note_with_no_title_is_dropped():
    note = _note()
    del note["content"]["title"]

    assert from_openreview(note) is None


def test_review_notes_are_dropped_by_their_invitation():
    review = _note(invitations=["ICLR.cc/2027/Conference/Paper7/-/Official_Review"])

    assert from_openreview(review) is None


def test_a_note_with_no_invitations_is_kept_only_when_it_carries_a_venue_id():
    with_venue = _note(invitations=[])
    without_venue = _note(invitations=[])
    del without_venue["content"]["venueid"]

    assert from_openreview(with_venue) is not None
    assert from_openreview(without_venue) is None


# --- requests ---------------------------------------------------------------------------------------------


async def test_the_request_sends_the_search_terms_and_never_an_email_or_key():
    transport, seen = _scripted(httpx.Response(200, json={"notes": [], "count": 0}))
    client = openreview.new_client(transport=transport)

    await openreview.search(client, "graph neural networks", 10)

    [request] = seen
    assert request.url.path == "/notes/search"
    assert dict(request.url.params) == {
        "term": "graph neural networks",
        "type": "terms",
        "content": "title",
        "source": "forum",
        "limit": "10",
        "offset": "0",
    }
    assert "authorization" not in request.headers
    assert "email" not in str(request.url).lower() and "key" not in request.url.params


async def test_search_page_sends_the_offset_it_was_given_and_stops_at_the_reported_count():
    transport, seen = _scripted(
        httpx.Response(200, json={"notes": [_note(id="a")] * 2, "count": 3}),
        httpx.Response(200, json={"notes": [_note(id="b")], "count": 3}),
    )
    client = openreview.new_client(transport=transport)

    _, next_cursor = await openreview.search_page(client, "gnn", 2, 0)
    _, last_cursor = await openreview.search_page(client, "gnn", 2, next_cursor)

    assert [r.url.params["offset"] for r in seen] == ["0", "2"]
    assert (next_cursor, last_cursor) == (2, None)


async def test_a_429_waits_retry_after_once_and_then_succeeds(fresh_budget_and_no_sleeps):
    transport, seen = _scripted(
        httpx.Response(429, headers={"retry-after": "7"}),
        httpx.Response(200, json={"notes": [_note()], "count": 1}),
    )
    client = openreview.new_client(transport=transport)

    notes, _ = await openreview.search_page(client, "gnn", 25, 0)

    assert len(notes) == 1
    assert len(seen) == 2
    assert fresh_budget_and_no_sleeps == [7.0]


async def test_a_second_429_fails_the_source_with_an_httpx_error(fresh_budget_and_no_sleeps):
    transport, seen = _scripted(
        httpx.Response(429, headers={"retry-after": "5"}),
        httpx.Response(429, headers={"retry-after": "5"}),
    )
    client = openreview.new_client(transport=transport)

    with pytest.raises(httpx.HTTPError) as caught:
        await openreview.search_page(client, "gnn", 25, 0)

    assert len(seen) == 2  # one retry, then give up
    assert fresh_budget_and_no_sleeps == [5.0]
    assert "api2.openreview.net" not in str(caught.value)  # the message never embeds the URL


async def test_a_429_with_no_retry_after_waits_one_full_window(fresh_budget_and_no_sleeps):
    transport, _ = _scripted(httpx.Response(429), httpx.Response(200, json={"notes": [], "count": 0}))

    await openreview.search(openreview.new_client(transport=transport), "gnn", 10)

    assert fresh_budget_and_no_sleeps == [openreview.RATE_WINDOW_SECONDS]


async def test_the_bucket_makes_a_twenty_first_request_wait_for_the_window(fresh_budget_and_no_sleeps):
    import time

    openreview._sent_at.extend([time.monotonic()] * openreview.RATE_LIMIT)

    await openreview._take_token()

    [wait] = fresh_budget_and_no_sleeps
    assert openreview.RATE_WINDOW_SECONDS - 1 < wait <= openreview.RATE_WINDOW_SECONDS


async def test_a_reply_without_notes_is_a_failed_source_not_an_empty_result():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"count": 3}))
    http = openreview.new_client(email=None, api_key=None, transport=transport)
    with pytest.raises(httpx.HTTPError):
        await openreview.search_page(http, "retrieval", 20, 0)
