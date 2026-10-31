import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert
from test_manuscript_papers import setup

from app.core import manuscript_papers, manuscripts, queue
from app.models import Note, note_anchors, note_papers
from app.workers import manuscript_section_review as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
ALLOWED = set(
    "id file section_hash title role role_source status reason findings kind point refs n hash preview note_id "
    "paper_id label dropped model ai created_at reviews sections start end words guess".split()
)
BANNED = {"text", "insert", "latex", "code", "tikz", "suggestion", "replacement", "rewrite", "wording"}
TEXT = (
    "\\section{Introduction}\nSleep is vital for health every night of the week. Sleep improves memory in adults.\n"
    "\\section{Methods}\nWe measured sleep for ten nights.\n"
)
# Review Focus 5: rewrites the parser must drop, between honest points.
REPLY = (
    "Missing: rewrite it as “Sleep is vital for health every night.”\n"
    "Rewrite it as: Sleep is vital.\n"
    "Missing: no sample size is named\n"
    "Supported: the aim is clear [S1] and noted [N1]\n"
    "Unsupported: the memory claim has no figure behind it [S2]\n"
)


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


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
        if "/section-review" in path:
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


async def test_responses_never_carry_text_for_the_researchers_prose(client, session, app):
    allowlist = response_properties(app.openapi())
    assert allowlist == ALLOWED, allowlist ^ ALLOWED
    assert not allowlist & BANNED

    _, papers, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    key = (await manuscript_papers.list_papers(session, m.id))[0]["key"]
    await manuscripts.upsert_text(session, m.id, "main.tex", TEXT)
    n = Note(body="Rewrite it as: Sleep is vital.", provenance="human")
    session.add(n)
    await session.flush()
    await session.execute(insert(note_papers).values(note_id=n.id, paper_id=papers[0].id))
    await session.execute(
        insert(note_anchors).values(note_id=n.id, paper_id=papers[0].id, page=4, bbox=[[1, 2, 3, 4]], quoted_text="q")
    )
    base = f"/api/manuscripts/{m.id}/section-review"
    stamp = (await manuscripts.read(session, m.id, "main.tex")).updated_at.isoformat()
    started = await client.post(base, json={"file": "main.tex", "base": stamp, "at": 3, "role": None})
    assert started.status_code == 202, started.text
    run = started.json()
    await worker.review_manuscript_section({"llm": Scripted(REPLY)}, run["id"])
    state = (await client.get(base, params={"file": "main.tex"})).json()
    cancelled = (await client.post(f"{base}/{run['id']}/cancel")).json()
    located = (await client.post(f"{base}/locate", json={"file": "main.tex", "text": TEXT})).json()

    for body in (run, state, cancelled, located):
        assert names(body) <= ALLOWED and not names(body) & BANNED
    (review,) = state["reviews"]
    assert review["status"] == "done" and review["dropped"] == 2 and review["ai"] is True
    assert [f["kind"] for f in review["findings"]] == ["missing", "supported", "unsupported"]
    stored = TEXT.replace("\\section{Introduction}\n", "")
    for f in review["findings"]:
        assert len(f["point"].split()) <= 25
        for r in f["refs"]:
            if r["kind"] == "sentence":
                assert r["preview"] and r["preview"] in stored and stored.split(r["preview"])[0].count(".") <= 1
            else:
                assert r["label"] == "Jane Smith 2021 p.4" and r["note_id"] == str(n.id)
    assert cancelled["status"] == "done"
    assert [s["title"] for s in located["sections"]] == ["Introduction", "Methods"]
    assert key


async def test_error_codes_and_extra_fields(client, session):
    _, _, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", TEXT)
    base = f"/api/manuscripts/{m.id}/section-review"
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    ok = {"file": "main.tex", "base": later, "at": 3}
    assert (await client.post(base, json=ok | {"extra": 1})).status_code == 422
    assert (await client.post(base, json=ok | {"at": -1})).status_code == 422
    bad = await client.post(base, json=ok | {"role": "bogus"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "unknown_role")
    assert (await client.post(f"{base}/{uuid.uuid4()}/cancel")).status_code == 404
    assert (
        await client.post(f"/api/manuscripts/{uuid.uuid4()}/section-review/locate", json={"file": "a", "text": "x"})
    ).status_code == 404
    assert (await client.post(base, json=ok)).status_code == 202
