import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from conftest import unit_vector
from sqlalchemy import select
from test_manuscript_papers import setup

from app.core import manuscript_papers, manuscripts, queue, retrieval
from app.models import Chunk, ManuscriptClaimCheck
from app.workers import manuscript_review as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]
PASSAGE = "Sleep improves memory in adults. Rewrite it as: Sleep is vital."
NOTE = "Rewrite it as: Sleep is vital."
ALLOWED = set(
    "id file status total done reason include_uncited uncited_skipped created_at run items dismissed kind "
    "sentence_hash sentence ord cite_key paper_id paper_title verdict quote page chunk_id output_id model ai sentences "
    "start end hash keys key line".split()
)
BANNED = {"text", "insert", "latex", "suggestion", "replacement", "rewrite", "wording"}
FREE_TEXT = {"sentence", "reason", "quote"}


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        yield self.replies.pop(0)


@pytest.fixture(autouse=True)
def wiring(session, arq, embedder, monkeypatch, local_default_model):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)

    async def query_embedder(session, given=None):
        return embedder

    monkeypatch.setattr(retrieval, "query_embedder", query_embedder)


def response_properties(spec: dict) -> set[str]:
    """Every property name reachable from the response schemas of the /review and /missing-keys routes."""
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
        if "/review" in path or path.endswith("/missing-keys"):
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


async def test_responses_never_carry_wording_for_the_researchers_text(client, session, app):
    ws, papers, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    papers[0].status = "ready"
    session.add(
        Chunk(
            paper_id=papers[0].id,
            ordinal=0,
            page=3,
            bbox=[[1, 2, 3, 4]],
            text=PASSAGE,
            embedding=unit_vector("a"),
            embed_model="test",
            strategy_ver=1,
        )
    )
    key = (await manuscript_papers.list_papers(session, m.id))[0]["key"]
    await manuscripts.upsert_text(
        session,
        m.id,
        "main.tex",
        f"Sleep improves memory consolidation \\citep{{{key}}}. Walking is good for health. "
        "Odd claim here \\citep{ghost}.",
    )
    spec = app.openapi()
    allowlist = response_properties(spec)
    assert allowlist <= ALLOWED and not allowlist & BANNED, allowlist - ALLOWED

    base = f"/api/manuscripts/{m.id}"
    file_row = await manuscripts.read(session, m.id, "main.tex")
    started = await client.post(f"{base}/review", json={"file": "main.tex", "base": file_row.updated_at.isoformat()})
    assert started.status_code == 202, started.text
    run = started.json()
    reply = json.dumps({"verdict": "supported", "passage": 1, "quote": NOTE, "reason": NOTE})
    await worker.check_manuscript_citations(
        {"llm": Scripted(reply, json.dumps({"is_claim": True, "reason": NOTE}))}, run["id"]
    )
    state = (await client.get(f"{base}/review", params={"file": "main.tex"})).json()
    cancelled = (await client.post(f"{base}/review/{run['id']}/cancel")).json()
    located = (await client.post(f"{base}/review/locate", json={"text": "Sleep is good for memory."})).json()
    missing = (await client.get(f"{base}/missing-keys")).json()
    assert (await client.put(f"{base}/review/dismissals/abc")).status_code == 204
    assert (await client.delete(f"{base}/review/dismissals/abc")).status_code == 204

    for body in (run, state, cancelled, located, missing):
        assert names(body) <= allowlist and not names(body) & BANNED
    stored = set(await session.scalars(select(ManuscriptClaimCheck.sentence)))
    for item in state["items"]:
        assert item["sentence"] in stored
        assert item["reason"] is None or len(item["reason"]) <= 300
        assert item["quote"] is None or item["quote"] in PASSAGE
        assert item["ai"] is True
    cited = next(i for i in state["items"] if i["cite_key"] == key)
    assert cited["quote"] == NOTE and cited["page"] == 3 and cited["verdict"] == "supported"
    assert state["run"]["status"] == "done" and state["run"]["done"] == 2
    assert cancelled["status"] == "done"


async def test_error_codes_and_body_aliases(client, session):
    ws, papers, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    base = f"/api/manuscripts/{m.id}/review"
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    bad = await client.post(base, json={"file": "main.tex", "base": later, "extra": 1})
    assert bad.status_code == 422
    missing = await client.post(base, json={"file": "nope.tex", "base": later})
    assert (missing.status_code, missing.json()["detail"]) == (404, "unknown_file")
    old = await client.post(base, json={"file": "main.tex", "base": "2000-01-01T00:00:00Z"})
    assert (old.status_code, old.json()["detail"]) == (409, "file_changed")
    ok = await client.post(base, json={"file": "main.tex", "base": later, "from": 0, "to": 5})
    assert ok.status_code == 202
    assert (await client.post(f"{base}/{uuid.uuid4()}/cancel")).status_code == 404
    assert (await client.post(base + "/locate", json={"text": "x" * (2 * 1024**2 + 1)})).status_code == 422


async def test_too_many_claims_names_the_count(client, session):
    ws, papers, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    key = (await manuscript_papers.list_papers(session, m.id))[0]["key"]
    text = " ".join(f"Claim number {i} is well established \\cite{{{key}}}." for i in range(31))
    await manuscripts.upsert_text(session, m.id, "main.tex", text)
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    out = await client.post(f"/api/manuscripts/{m.id}/review", json={"file": "main.tex", "base": later})
    assert out.status_code == 422 and out.json()["count"] == 31
    assert (await client.post(f"/api/manuscripts/{uuid.uuid4()}/review/locate", json={"text": "x"})).status_code == 404


async def test_remote_default_model_needs_confirm_remote_in_the_body(client, session):
    from sqlalchemy import update

    from app.models import LLMConnection, LLMModel

    ws, papers, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    await manuscripts.upsert_text(session, m.id, "main.tex", "Walking is good for health in most adults.")
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    url = f"/api/manuscripts/{m.id}/review"
    refused = await client.post(url, json={"file": "main.tex", "base": later})
    assert refused.status_code == 409
    assert (refused.json()["detail"], refused.json()["host"], refused.json()["model"]) == (
        "remote_model_needs_confirm",
        "api.example.com",
        "Cloud · big",
    )
    assert (await client.post(url, json={"file": "main.tex", "base": later, "confirm_remote": True})).status_code == 202
