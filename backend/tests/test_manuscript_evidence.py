import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from conftest import unit_vector
from sqlalchemy import delete, select, update

from app.core import manuscript_evidence as ev
from app.core import manuscript_papers, manuscripts, queue, retrieval, workspaces
from app.core.errors import Conflict, InvalidInput
from app.models import Chunk, LLMModel, LLMOutput, Manuscript, ManuscriptEvidence, Paper, Workspace
from app.workers import manuscript_evidence as worker

pytestmark = pytest.mark.anyio
SENTENCE = "Sleep helps memory."


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield reply


def verdict(v="supported", quote="", reason="Because."):
    return json.dumps({"verdict": v, "passage": None, "quote": quote, "reason": reason})


@pytest.fixture(autouse=True)
def wiring(session, arq, embedder, monkeypatch):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)

    async def query_embedder(session, given=None):
        return embedder

    monkeypatch.setattr(retrieval, "query_embedder", query_embedder)


async def library(session, embedder, *titles, with_ws=True):
    """Papers in a workspace, closest to SENTENCE first; one chunk each (two for the first)."""
    ws = Workspace(name=f"W {uuid.uuid4().hex[:6]}")
    session.add(ws)
    await session.flush()
    embedder.vectors[f"search_query: {SENTENCE}"] = unit_vector("q")
    papers = []
    for i, title in enumerate(titles):
        p = Paper(title=title, file_path="/x.pdf", authors=["Jane Smith"], year=2021, status="ready")
        session.add(p)
        await session.flush()
        await workspaces.add_paper(session, ws.id, p.id)
        for j in range(2 if i == 0 else 1):
            vec = unit_vector("q") if j == 0 and i == 0 else unit_vector(f"far{i}{j}")
            session.add(Chunk(paper_id=p.id, ordinal=j, page=j + 1, bbox=[[1, 2, 3, 4]], text=f"{title} passage {j}",
                              embedding=vec, embed_model="test", strategy_ver=1))
        papers.append(p)
    await session.flush()
    m = await manuscripts.create(session, title="M", template="article", workspace_id=ws.id if with_ws else None)
    return papers, m


async def all_rows(session, mid):
    return list(await session.scalars(
        select(ManuscriptEvidence).where(ManuscriptEvidence.manuscript_id == mid)
        .order_by(ManuscriptEvidence.rank).execution_options(populate_existing=True)
    ))


async def test_papers_are_grouped_in_rank_order_with_their_keys(session, embedder, local_default_model, arq):
    papers, m = await library(session, embedder, "Alpha", "Beta")
    out = await ev.find(session, m.id, f"  {SENTENCE} ", embedder=embedder)
    assert [p["paper_id"] for p in out["papers"]] == [papers[0].id, papers[1].id]
    assert {p["key"] for p in out["papers"]} == {r["key"] for r in await manuscript_papers.list_papers(session, m.id)}
    first = out["papers"][0]["passages"]
    assert [x["page"] for x in first] == [1, 2] and first[0]["text"] == "Alpha passage 0"
    assert out["verdicts"] == "queued" and out["sentence_hash"] == ev.sentence_hash("sleep   helps memory.")
    assert arq.jobs == [("verify_manuscript_evidence", str(m.id), out["sentence_hash"])]
    assert [(r.status, r.rank) for r in await all_rows(session, m.id)] == [("queued", 0), ("queued", 1)]


async def test_no_workspace_and_empty_sentence_are_refused(session, embedder):
    _, m = await library(session, embedder, "Alpha", with_ws=False)
    with pytest.raises(InvalidInput, match="no_workspace"):
        await ev.find(session, m.id, SENTENCE, embedder=embedder)
    _, m = await library(session, embedder, "Alpha")
    with pytest.raises(InvalidInput, match="empty_claim"):
        await ev.find(session, m.id, "  ", embedder=embedder)
    with pytest.raises(InvalidInput, match="claim_too_long"):
        await ev.find(session, m.id, "x" * 2001, embedder=embedder)


async def test_no_default_model_shows_passages_and_queues_nothing(session, embedder, arq):
    await session.execute(update(LLMModel).values(is_default=False))
    _, m = await library(session, embedder, "Alpha")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    assert out["verdicts"] == "unavailable" and len(out["papers"]) == 1 and arq.jobs == []
    assert await all_rows(session, m.id) == [] and await ev.rows(session, m.id, out["sentence_hash"]) == []


async def test_asking_twice_keeps_one_row_per_paper_and_done_rows(session, embedder, local_default_model):
    papers, m = await library(session, embedder, "Alpha", "Beta")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    first = (await all_rows(session, m.id))[0]
    first.status, first.verdict = "done", "supported"
    await session.flush()
    again = await ev.find(session, m.id, f"  {SENTENCE}\n", embedder=embedder)
    assert again["sentence_hash"] == out["sentence_hash"]
    rows = await all_rows(session, m.id)
    assert [(r.paper_id, r.status, r.verdict) for r in rows] == [(papers[0].id, "done", "supported"),
                                                                  (papers[1].id, "queued", None)]


async def test_job_checks_papers_in_rank_order_and_marks_failures(session, embedder, local_default_model):
    papers, m = await library(session, embedder, "Alpha", "Beta", "Gamma")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    llm = Scripted(verdict("not_addressed", reason="Nothing."), "not json", "still not json", verdict("not_supported"))
    await worker.verify_manuscript_evidence({"llm": llm}, str(m.id), out["sentence_hash"])
    rows = await all_rows(session, m.id)
    assert [r.paper_id for r in rows] == [p.id for p in papers]
    assert [(r.status, r.verdict) for r in rows] == [("done", "not_addressed"), ("done", "cannot_verify"),
                                                      ("done", "not_supported")]
    assert rows[0].reason == "Nothing." and rows[0].output_id is not None
    assert [r["status"] for r in await ev.rows(session, m.id, out["sentence_hash"])] == ["done"] * 3


async def test_job_failure_is_that_rows_failure_and_the_rest_run(session, embedder, local_default_model):
    papers, m = await library(session, embedder, "Alpha", "Beta")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    llm = Scripted(RuntimeError("boom"), verdict("supported"))
    await worker.verify_manuscript_evidence({"llm": llm}, str(m.id), out["sentence_hash"])
    rows = await all_rows(session, m.id)
    assert [(r.status, r.reason) for r in rows] == [("failed", "check_failed"), ("done", "Because.")]


async def test_job_skips_a_row_a_newer_ask_already_finished(session, embedder, local_default_model):
    papers, m = await library(session, embedder, "Alpha", "Beta")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)

    class Newer(Scripted):  # while the model "thinks", a newer ask finishes the row the job is on
        async def stream(self, system, prompt):
            await session.execute(update(ManuscriptEvidence).where(ManuscriptEvidence.rank == 0)
                                  .values(status="done", verdict="supported", reason="newer"))
            async for x in super().stream(system, prompt):
                yield x

    await worker.verify_manuscript_evidence({"llm": Newer(verdict("not_supported"), verdict("supported"))},
                                            str(m.id), out["sentence_hash"])
    rows = await all_rows(session, m.id)
    assert (rows[0].verdict, rows[0].reason) == ("supported", "newer")
    assert rows[1].status == "done"


async def test_a_long_running_row_reads_as_interrupted(session, embedder, local_default_model):
    _, m = await library(session, embedder, "Alpha")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    old = datetime.now(UTC) - timedelta(minutes=6)
    await session.execute(update(ManuscriptEvidence).values(status="running", updated_at=old))
    assert [r["status"] for r in await ev.rows(session, m.id, out["sentence_hash"])] == ["interrupted"]
    await session.execute(update(ManuscriptEvidence).values(updated_at=datetime.now(UTC)))
    assert [r["status"] for r in await ev.rows(session, m.id, out["sentence_hash"])] == ["running"]
    await age(session, 6)
    await ev.find(session, m.id, SENTENCE, embedder=embedder)  # asking again starts an interrupted row over
    assert (await all_rows(session, m.id))[0].status == "queued"


async def age(session, minutes, **values):
    await session.execute(update(ManuscriptEvidence).values(
        updated_at=datetime.now(UTC) - timedelta(minutes=minutes), **values))


async def test_a_queued_row_nobody_picked_up_reads_as_interrupted(session, embedder, local_default_model):
    _, m = await library(session, embedder, "Alpha")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    assert [r["status"] for r in await ev.rows(session, m.id, out["sentence_hash"])] == ["queued"]
    await age(session, 6)
    assert [r["status"] for r in await ev.rows(session, m.id, out["sentence_hash"])] == ["interrupted"]
    await ev.find(session, m.id, SENTENCE, embedder=embedder)
    assert [r["status"] for r in await ev.rows(session, m.id, out["sentence_hash"])] == ["queued"]


async def test_a_queue_that_is_down_fails_the_rows_and_says_unavailable(session, embedder, local_default_model, arq):
    async def down(*args, **kwargs):
        raise ConnectionError("redis is gone")

    arq.enqueue_job = down
    _, m = await library(session, embedder, "Alpha", "Beta")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)
    assert out["verdicts"] == "unavailable" and len(out["papers"]) == 2
    assert [(r.status, r.reason) for r in await all_rows(session, m.id)] == [("failed", "queue_unavailable")] * 2


async def test_asking_again_leaves_a_running_check_alone_but_restarts_failed_ones(session, embedder,
                                                                                  local_default_model):
    _, m = await library(session, embedder, "Alpha", "Beta")
    await ev.find(session, m.id, SENTENCE, embedder=embedder)
    first, second = await all_rows(session, m.id)
    first.status, second.status, second.reason = "running", "failed", "check_failed"
    await session.flush()
    await ev.find(session, m.id, SENTENCE, embedder=embedder)
    rows = await all_rows(session, m.id)
    assert [(r.status, r.reason) for r in rows] == [("running", None), ("queued", None)]


async def test_a_model_error_fails_that_row_with_its_code(session, embedder, local_default_model):
    _, m = await library(session, embedder, "Alpha")
    out = await ev.find(session, m.id, SENTENCE, embedder=embedder)

    class NoModel(Scripted):
        async def stream(self, system, prompt):
            raise Conflict("no_model")
            yield

    await worker.verify_manuscript_evidence({"llm": NoModel()}, str(m.id), out["sentence_hash"])
    assert [(r.status, r.reason) for r in await all_rows(session, m.id)] == [("failed", "no_model")]


async def test_two_jobs_on_real_connections_check_every_paper_once(monkeypatch):
    from app.db import SessionLocal
    monkeypatch.setattr(worker, "SessionLocal", SessionLocal)
    async with SessionLocal() as s:
        ws = Workspace(name=f"W {uuid.uuid4().hex[:6]}")
        s.add(ws)
        await s.flush()
        m = await manuscripts.create(s, title="M", template="article", workspace_id=ws.id)
        papers = [Paper(title=f"P{i}", file_path="/x.pdf", status="ready") for i in range(3)]
        s.add_all(papers)
        await s.flush()
        for i, p in enumerate(papers):
            s.add(Chunk(paper_id=p.id, ordinal=0, page=1, bbox=[[1, 2, 3, 4]], text=f"text {i}",
                        embedding=unit_vector(f"c{i}"), embed_model="test", strategy_ver=1))
            s.add(ManuscriptEvidence(manuscript_id=m.id, sentence_hash="h", sentence=SENTENCE, paper_id=p.id,
                                     rank=i, status="queued"))
        await s.commit()
        mid, pids = m.id, [p.id for p in papers]

    class Counting:
        model, connection_name = "fake:counting", "Test"
        calls = 0

        async def stream(self, system, prompt):
            Counting.calls += 1
            await asyncio.sleep(0.05)
            yield verdict("not_addressed")

    try:
        await asyncio.gather(*(worker.verify_manuscript_evidence({"llm": Counting()}, str(mid), "h")
                               for _ in range(2)))
        async with SessionLocal() as s:
            statuses = list(await s.scalars(select(ManuscriptEvidence.status).where(
                ManuscriptEvidence.manuscript_id == mid)))
        assert Counting.calls == 3 and statuses == ["done"] * 3
    finally:
        async with SessionLocal() as s:
            await s.execute(delete(LLMOutput).where(LLMOutput.paper_id.in_(pids)))
            await s.execute(delete(Manuscript).where(Manuscript.id == mid))  # its evidence goes with it
            await s.execute(delete(Paper).where(Paper.id.in_(pids)))
            await s.execute(delete(Workspace).where(Workspace.id == ws.id))
            await s.commit()
