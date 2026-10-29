"""The triage desk over HTTP: decisions, undo, late reason, history, summary and the reading source header."""

import uuid
from datetime import timedelta

import pytest
from mcp import Client
from sqlalchemy import func, select

from app.models import Paper, PaperMerge, TriageEvent
from mcp_server import server

pytestmark = pytest.mark.anyio

PILES = {
    "read_closely": ("keep", 0),
    "skim": ("keep", 1),
    "later": ("later", 0),
    "not_relevant": ("drop", 0),
    "skip": (None, 0),
}


async def make(session, **kw) -> Paper:
    paper = Paper(title="P", **kw)
    session.add(paper)
    await session.commit()
    return paper


def body(pile="skim", sid=None, **kw):
    if pile == "not_relevant":
        kw.setdefault("reason", "off_topic")
    return {"pile": pile, "session_id": str(sid or uuid.uuid4()), **kw}


def decide(client, paper, **kw):
    return client.post(f"/api/papers/{paper.id}/triage-decisions", json=body(**kw))


async def events(session, paper_id) -> int:
    return await session.scalar(select(func.count()).select_from(TriageEvent).where(TriageEvent.paper_id == paper_id))


@pytest.mark.parametrize("pile", PILES)
async def test_each_pile_answers_201_and_the_paper_shows_it(client, session, pile):
    paper = await make(session)
    response = await decide(client, paper, pile=pile)
    assert response.status_code == 201
    assert response.json()["event"]["pile"] == pile and response.json()["event"]["source"] == "desk"
    got = (await client.get(f"/api/papers/{paper.id}")).json()
    assert response.json()["paper"]["id"] == got["id"]
    assert (got["triage"], got["reading_pass"]) == (PILES[pile][0], PILES[pile][1])


async def test_a_drop_stays_in_the_library_list(client, session):
    paper = await make(session)
    await decide(client, paper, pile="not_relevant")
    listed = {p["id"]: p for p in (await client.get("/api/papers")).json()}
    assert listed[str(paper.id)]["triage"] == "drop"


@pytest.mark.parametrize(
    "extra, code, allowed",
    [
        ({"pile": "not_relevant", "reason": None}, "reason_required", True),
        ({"pile": "not_relevant", "reason": "nope"}, "unknown_reason", True),
        ({"pile": "skim", "reason": "off_topic"}, "unknown_reason", True),
        ({"pile": "skim", "note": "x" * 501}, "note_too_long", False),
    ],
)
async def test_decision_422_codes(client, session, extra, code, allowed):
    paper = await make(session)
    response = await client.post(f"/api/papers/{paper.id}/triage-decisions", json={**body(), **extra})
    assert response.status_code == 422
    assert response.json()["detail"] == code
    assert ("allowed" in response.json()) is allowed
    assert await events(session, paper.id) == 0


@pytest.mark.parametrize("extra", [{"pile": "later_maybe"}, {"bogus": 1}, {"session_id": "nope"}])
async def test_decision_shape_errors_are_422(client, session, extra):
    paper = await make(session)
    response = await client.post(f"/api/papers/{paper.id}/triage-decisions", json={**body(), **extra})
    assert response.status_code == 422


async def test_unknown_paper_and_event_are_404(client):
    assert (await client.post(f"/api/papers/{uuid.uuid4()}/triage-decisions", json=body())).status_code == 404
    assert (await client.get(f"/api/papers/{uuid.uuid4()}/triage-events")).status_code == 404
    assert (await client.patch(f"/api/triage-events/{uuid.uuid4()}", json={"note": "x"})).status_code == 404
    assert (await client.post(f"/api/triage-events/{uuid.uuid4()}/undo")).status_code == 404


async def test_a_merged_id_is_410_with_kept_id(client, session):
    kept, gone = uuid.uuid4(), uuid.uuid4()
    session.add(PaperMerge(kept_id=kept, merged_id=gone, status="merged"))
    await session.flush()
    response = await client.post(f"/api/papers/{gone}/triage-decisions", json=body())
    assert response.status_code == 410 and response.json()["kept_id"] == str(kept)


async def test_replay_with_the_same_client_id_is_200_and_logs_once(client, session):
    paper = await make(session)
    sid, cid = uuid.uuid4(), str(uuid.uuid4())
    first = await decide(client, paper, sid=sid, client_id=cid)
    again = await decide(client, paper, sid=sid, client_id=cid)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["event"]["id"] == again.json()["event"]["id"]
    assert await events(session, paper.id) == 1


async def test_undo_then_already_undone(client, session):
    paper = await make(session, triage="drop", reading_pass=2)
    event = (await decide(client, paper, pile="later")).json()["event"]
    undone = await client.post(f"/api/triage-events/{event['id']}/undo")
    assert undone.status_code == 200
    assert (undone.json()["paper"]["triage"], undone.json()["event"]["source"]) == ("drop", "undo")
    again = await client.post(f"/api/triage-events/{event['id']}/undo")
    assert (again.status_code, again.json()["detail"]) == (409, "already_undone")


async def test_undo_after_a_reading_change_is_changed_since(client, session):
    paper = await make(session)
    event = (await decide(client, paper, pile="skim")).json()["event"]
    assert (await client.put(f"/api/papers/{paper.id}/reading", json={"triage": "drop"})).status_code == 200
    response = await client.post(f"/api/triage-events/{event['id']}/undo")
    assert (response.status_code, response.json()["detail"]) == (409, "changed_since")


async def test_undoing_a_non_desk_event_is_409(client, session):
    paper = await make(session)
    await client.put(f"/api/papers/{paper.id}/reading", json={"triage": "keep"})
    reader = (await client.get(f"/api/papers/{paper.id}/triage-events")).json()["events"][0]
    response = await client.post(f"/api/triage-events/{reader['id']}/undo")
    assert (response.status_code, response.json()["detail"]) == (409, "not_a_desk_event")


async def test_patch_adds_a_reason_inside_the_window_and_refuses_outside(client, session):
    paper = await make(session)
    event = (await decide(client, paper, pile="not_relevant")).json()["event"]
    ok = await client.patch(f"/api/triage-events/{event['id']}", json={"reason": "duplicate", "note": "same as X"})
    assert ok.status_code == 200 and (ok.json()["reason"], ok.json()["note"]) == ("duplicate", "same as X")
    kept = await client.patch(f"/api/triage-events/{event['id']}", json={"note": "later"})
    assert kept.json()["reason"] == "duplicate"  # reason not sent: left alone
    blank = await client.patch(f"/api/triage-events/{event['id']}", json={"reason": None})
    assert (blank.status_code, blank.json()["detail"]) == (422, "reason_required")
    row = await session.get(TriageEvent, uuid.UUID(event["id"]))
    row.created_at = row.created_at.replace(year=2020)
    await session.commit()
    late = await client.patch(f"/api/triage-events/{event['id']}", json={"note": "x"})
    assert (late.status_code, late.json()["detail"]) == (409, "late_reason_window")


async def test_history_is_newest_first(client, session):
    paper = await make(session)
    first = (await decide(client, paper, pile="later")).json()["event"]
    row = await session.get(TriageEvent, uuid.UUID(first["id"]))
    row.created_at = row.created_at - timedelta(minutes=1)  # one test transaction: now() would tie
    await session.commit()
    await decide(client, paper, pile="skim")
    got = (await client.get(f"/api/papers/{paper.id}/triage-events")).json()["events"]
    assert [e["pile"] for e in got] == ["skim", "later"]


async def test_summary_after_two_decisions_one_undo_and_one_skip(client, session):
    sid = uuid.uuid4()
    a, b, c = await make(session), await make(session), await make(session)
    first = (await decide(client, a, pile="skim", sid=sid, card_ms=1000, pdf_opened=True)).json()["event"]
    await decide(client, b, pile="later", sid=sid, card_ms=2000)
    await decide(client, c, pile="skip", sid=sid, card_ms=500)
    await client.post(f"/api/triage-events/{first['id']}/undo")
    got = (await client.get("/api/triage-summary", params={"session_id": str(sid)})).json()
    assert got == {"per_pile": {"later": 1}, "skipped": 1, "decided": 1, "card_ms": 2500, "pdf_opened": 0}
    assert (await client.get("/api/triage-summary", params={"session_id": "nope"})).status_code == 422


@pytest.mark.parametrize("headers, stored", [({"X-PaperLab-Source": "library"}, "library"), ({}, "reader")])
async def test_reading_source_header(client, session, headers, stored):
    paper = await make(session)
    response = await client.put(f"/api/papers/{paper.id}/reading", json={"triage": "keep"}, headers=headers)
    assert response.status_code == 200
    assert (await client.get(f"/api/papers/{paper.id}/triage-events")).json()["events"][0]["source"] == stored


async def test_reading_unknown_source_is_422_and_logs_nothing(client, session):
    paper = await make(session)
    response = await client.put(
        f"/api/papers/{paper.id}/reading", json={"triage": "keep"}, headers={"X-PaperLab-Source": "x"}
    )
    assert (response.status_code, response.json()["detail"]) == (422, "unknown_source")
    assert response.json()["allowed"] == ["reader", "library"]
    assert await events(session, paper.id) == 0


async def test_openapi_lists_the_new_paths_and_mcp_has_no_triage_tool(client):
    paths = (await client.get("/openapi.json")).json()["paths"]
    for path in (
        "/api/papers/{paper_id}/triage-decisions",
        "/api/papers/{paper_id}/triage-events",
        "/api/triage-events/{event_id}",
        "/api/triage-events/{event_id}/undo",
        "/api/triage-summary",
    ):
        assert path in paths
    async with Client(server.mcp) as mcp:
        names = [tool.name for tool in (await mcp.list_tools()).tools]
    assert not [n for n in names if "triage" in n]


def test_card_ms_above_the_cap_is_clamped_not_refused():
    from app.schemas.triage import CARD_MS_CAP, TriageDecisionIn

    body = {"pile": "skim", "session_id": str(uuid.uuid4())}
    assert TriageDecisionIn(**body, card_ms=CARD_MS_CAP * 10).card_ms == CARD_MS_CAP
    assert TriageDecisionIn(**body, card_ms=5).card_ms == 5


def test_the_request_pile_literal_matches_the_core_piles():
    from typing import get_args

    from app.core import triage
    from app.schemas.triage import TriageDecisionIn

    assert get_args(TriageDecisionIn.model_fields["pile"].annotation) == tuple(triage.PILES)
