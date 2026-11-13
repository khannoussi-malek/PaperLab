import json
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from test_manuscript_papers import setup

from app.core import manuscripts, queue
from app.models import ManuscriptDraftReview as Row
from app.workers import manuscript_draft_review as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
ALLOWED = set(
    "id mode status stage calls_done calls_max reason issues refuted counts model ai created_at review "
    "severity section summary quote close_criterion raised_by file line max_calls likely_calls paper_chars "
    "approx_input_tokens too_long modes parts".split()
)
BANNED = {"text", "insert", "latex", "code", "tikz", "suggestion", "replacement", "rewrite", "wording"}
BODY = (
    "\\begin{document}\n\\section{Intro}\n"
    + " ".join(f"Sentence {i} claims that sleep improves memory." for i in range(12))
    + "\n\\end{document}\n"
)
ISSUE = {
    "severity": "major",
    "section": "Intro",
    "summary": "The memory claim has no figure behind it",
    "evidence_quote": "Sentence 3 claims that sleep improves memory",
    "close_criterion": "The claim must point to a number",
}


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        reply = self.replies.pop(0) if self.replies else '{"refuted": false, "reason": "fair"}'
        yield reply if isinstance(reply, str) else json.dumps(reply)


@pytest.fixture(autouse=True)
def wiring(session, arq, monkeypatch, local_default_model):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)


def response_properties(spec: dict) -> set[str]:
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(spec["components"]["schemas"][node["$ref"].rsplit("/", 1)[1]])
            found.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path, methods in spec["paths"].items():
        if "/draft-review" in path:
            for op in methods.values():
                for code, response in op["responses"].items():
                    if code.startswith("2"):
                        walk(response.get("content", {}))
    return found


def names(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {n for v in value.values() for n in names(v)}
    if isinstance(value, list):
        return {n for v in value for n in names(v)}
    return set()


async def manuscript(session, text=BODY):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", text)
    return m


async def test_responses_never_carry_text_for_the_researchers_prose(client, session, app):
    allowlist = response_properties(app.openapi())
    assert allowlist == ALLOWED, allowlist ^ ALLOWED
    assert not allowlist & BANNED
    m = await manuscript(session)
    base = f"/api/manuscripts/{m.id}/draft-review"
    started = (await client.post(base, json={"confirm_remote": False})).json()
    assert not names(started) & BANNED
    llm = Scripted({"issues": [ISSUE]}, {"issues": []}, {"issues": []})
    await worker.review_manuscript_draft({"llm": llm}, str(started["id"]))
    state = (await client.get(base)).json()
    assert not names(state) & BANNED
    assert state["review"]["issues"][0]["file"] == "main.tex"


async def test_start_state_estimate_and_cancel(client, session, arq):
    m = await manuscript(session)
    base = f"/api/manuscripts/{m.id}/draft-review"
    assert (await client.get(base)).json() == {"review": None}
    started = await client.post(base, json={"confirm_remote": False})
    assert (started.status_code, started.json()["status"]) == (202, "queued")
    assert (await client.get(base)).json()["review"]["status"] == "queued"
    est = (await client.get(f"{base}/estimate")).json()
    assert est["too_long"] is False
    assert [(x["mode"], x["likely_calls"], x["max_calls"]) for x in est["modes"]] == [
        ("light", 11, 11),
        ("full", 42, 54),
    ]
    cancelled = (await client.post(f"{base}/{started.json()['id']}/cancel")).json()
    assert (cancelled["status"], cancelled["reason"]) == ("failed", "cancelled")
    assert (await client.post(f"{base}/{uuid.uuid4()}/cancel")).status_code == 404


async def test_error_codes_and_extra_fields(client, session):
    m = await manuscript(session)
    base = f"/api/manuscripts/{m.id}/draft-review"
    assert (await client.post(base, json={"extra": 1})).status_code == 422
    assert (await client.post(base, json={"mode": "heavy"})).status_code == 422
    unknown = await client.post(f"/api/manuscripts/{uuid.uuid4()}/draft-review", json={})
    assert unknown.status_code == 404
    assert (await client.post(f"{base}/{uuid.uuid4()}/cancel")).json()["detail"] == "unknown_review"


async def test_a_live_review_answers_409_and_full_needs_a_confirm(client, session, arq):
    m = await manuscript(session)
    base = f"/api/manuscripts/{m.id}/draft-review"
    assert (await client.post(base, json={})).status_code == 202
    again = await client.post(base, json={})
    assert (again.status_code, again.json()["detail"]) == (409, "review_running")
    rows_before = list(await session.scalars(select(Row).where(Row.manuscript_id == m.id)))
    other = await manuscript(session)
    refused = await client.post(f"/api/manuscripts/{other.id}/draft-review", json={"mode": "full"})
    assert refused.status_code == 409
    assert refused.json() == {"detail": "full_needs_confirm", "likely_calls": 42, "max_calls": 54}
    assert await session.scalar(select(Row).where(Row.manuscript_id == other.id)) is None
    assert len(rows_before) == 1
    ok = await client.post(f"/api/manuscripts/{other.id}/draft-review", json={"mode": "full", "confirm_full": True})
    assert (ok.status_code, ok.json()["mode"], ok.json()["calls_max"]) == (202, "full", 54)


async def test_a_long_paper_answers_422(client, session):
    m = await manuscript(session, "\\begin{document}\n" + "w" * 160_001 + "\n\\end{document}\n")
    refused = await client.post(f"/api/manuscripts/{m.id}/draft-review", json={})
    assert (refused.status_code, refused.json()["detail"]) == (422, "paper_too_long")
