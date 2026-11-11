import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import delete, update
from test_manuscript_papers import setup

from app.core import manuscript_papers, manuscripts, queue, retrieval
from app.models import ManuscriptClaimCheck, ManuscriptFile
from app.workers import manuscript_review as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]


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


async def bare(session, text_fn):
    """A manuscript whose only .tex file is main.tex (the article template's sections are removed)."""
    ws, papers, m = await setup(session, "Alpha", name=f"W {uuid.uuid4().hex[:8]}")
    key = (await manuscript_papers.list_papers(session, m.id))[0]["key"]
    await session.execute(
        delete(ManuscriptFile).where(ManuscriptFile.manuscript_id == m.id, ManuscriptFile.path.like("sections/%"))
    )
    await manuscripts.upsert_text(session, m.id, "main.tex", text_fn(key))
    await session.flush()
    return m


async def test_estimate_then_start_the_whole_manuscript(client, session):
    m = await bare(
        session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}. Walking is good for health."
    )
    base = f"/api/manuscripts/{m.id}/review/all"
    est = await client.get(f"{base}/estimate")
    assert est.status_code == 200
    body = est.json()
    assert [f["path"] for f in body["files"]] == ["main.tex"]
    assert body["pairs"] == 1 and body["needs_confirm"] is False
    started = await client.post(base, json={})
    assert started.status_code == 202 and started.json()["file"] == "*"


async def test_more_than_30_checks_need_confirm_large(client, session):
    m = await bare(
        session, lambda k: " ".join(f"Claim number {i} is well established \\cite{{{k}}}." for i in range(31))
    )
    base = f"/api/manuscripts/{m.id}/review/all"
    out = await client.post(base, json={})
    assert out.status_code == 422 and out.json()["detail"] == "confirm_large" and out.json()["count"] == 31
    assert (await client.post(base, json={"confirm_large": True})).status_code == 202


async def test_report_json_and_markdown(client, session):
    m = await bare(
        session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}. Plain words are written here."
    )
    base = f"/api/manuscripts/{m.id}"
    assert (await client.post(f"{base}/review/all", json={})).status_code == 202
    await session.execute(
        update(ManuscriptClaimCheck)
        .where(ManuscriptClaimCheck.manuscript_id == m.id, ManuscriptClaimCheck.kind == "cited")
        .values(status="done", verdict="supported")
    )
    await session.flush()
    report = (await client.get(f"{base}/review/report")).json()
    assert [f["path"] for f in report["files"]] == ["main.tex"]
    assert report["counts"] == {"supported": 1, "unfinished": 1}
    md = await client.get(f"{base}/review/report.md")
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "citation-review.md" in md.headers["content-disposition"]
    assert md.text.startswith("# Citation review")


async def test_report_without_a_run_is_404(client, session):
    m = await bare(session, lambda k: "Plain words are written here.")
    out = await client.get(f"/api/manuscripts/{m.id}/review/report")
    assert (out.status_code, out.json()["detail"]) == (404, "unknown_run")


async def test_the_file_view_after_an_all_run_shows_that_file(client, session):
    m = await bare(session, lambda k: f"Sleep improves memory consolidation \\citep{{{k}}}.")
    base = f"/api/manuscripts/{m.id}/review"
    assert (await client.post(f"{base}/all", json={})).status_code == 202
    state = (await client.get(base, params={"file": "main.tex"})).json()
    assert state["run"]["file"] == "*"
    assert state["items"] and all(i["file"] == "main.tex" for i in state["items"])


async def test_the_estimate_route_is_not_taken_for_a_run_id(client, session):
    m = await bare(session, lambda k: "Plain words are written here.")
    out = await client.get(f"/api/manuscripts/{m.id}/review/all/estimate")
    assert out.status_code == 200 and "pairs" in out.json()
