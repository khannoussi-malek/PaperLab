import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_DATABASE_URL, unit_vector
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_manuscript_papers import setup

from app.core import manuscript_papers, manuscripts, queue, retrieval
from app.core import manuscript_review as mr
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import (
    Chunk,
    ManuscriptClaimCheck,
    ManuscriptReviewRun,
)
from app.workers import manuscript_review as worker

pytestmark = pytest.mark.anyio
FUTURE = datetime.now(UTC) + timedelta(days=1)


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def stream(self, system, prompt):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield reply


def check(v="supported", reason="Because."):
    return json.dumps({"verdict": v, "passage": None, "quote": "", "reason": reason})


def claim(flag=True):
    return json.dumps({"is_claim": flag, "reason": "r"})


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


async def doc(session, text_fn, *titles):
    _, papers, m = await setup(session, *titles, name=f"W {uuid.uuid4().hex[:8]}")
    for p in papers:
        p.status = "ready"
        session.add(
            Chunk(
                paper_id=p.id,
                ordinal=0,
                page=1,
                bbox=[[1, 2, 3, 4]],
                text=f"{p.title} passage",
                embedding=unit_vector(p.title),
                embed_model="test",
                strategy_ver=1,
            )
        )
    await session.flush()
    keys = [r["key"] for r in await manuscript_papers.list_papers(session, m.id)]
    await manuscripts.upsert_text(session, m.id, "main.tex", text_fn(keys))
    return papers, keys, m


def basic(keys):
    a, b = keys[0], keys[1]
    return (
        f"Sleep improves memory consolidation \\citep{{{a}}}. Coffee boosts focus in adults \\citep{{{a},{b}}}. "
        "Walking is good for health. Many people sleep eight hours \\citep{ghost}."
    )


async def go(session, m, **kw):
    kw = {"file": "main.tex", "base": FUTURE, "selection": None} | kw
    return await mr.start(session, m.id, **kw)


async def rows(session, mid):
    return list(
        await session.scalars(
            select(ManuscriptClaimCheck)
            .where(ManuscriptClaimCheck.manuscript_id == mid)
            .order_by(ManuscriptClaimCheck.ord)
            .execution_options(populate_existing=True)
        )
    )


async def test_one_row_per_sentence_and_paper_and_unresolved_keys_finish(session, arq):
    papers, keys, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m)
    got = await rows(session, m.id)
    assert [(r.kind, r.cite_key, r.status) for r in got] == [
        ("cited", keys[0], "queued"),
        ("cited", keys[0], "queued"),
        ("cited", keys[1], "queued"),
        ("cited", "ghost", "done"),
        ("uncited", None, "queued"),
    ]
    ghost = got[3]
    assert (ghost.verdict, ghost.reason, ghost.paper_id) == ("cannot_verify", "key_not_found", None)
    assert run["status"] == "queued" and run["total"] == 5 and run["done"] == 1
    assert arq.jobs == [("check_manuscript_citations", str(run["id"]))]
    assert [r.ord for r in got] == [0, 1, 2, 3, 4]


async def test_thirty_pairs_pass_and_thirty_one_refuse_with_nothing_written(session):
    def cites(n):
        return lambda keys: " ".join(f"Claim number {i} is well established \\cite{{{keys[0]}}}." for i in range(n))

    papers, keys, m = await doc(session, cites(30), "Alpha")
    assert (await go(session, m))["total"] == 30
    papers, keys, m = await doc(session, cites(31), "Alpha")
    with pytest.raises(InvalidInput, match="too_many_claims") as exc:
        await go(session, m)
    assert exc.value.details["count"] == 31
    assert await rows(session, m.id) == []
    assert not await session.scalar(select(ManuscriptReviewRun.id).where(ManuscriptReviewRun.manuscript_id == m.id))


async def test_unresolved_keys_do_not_count_and_uncited_never_refuse(session):
    text = " ".join(f"Claim number {i} is well established \\cite{{nope{i}}}." for i in range(40))
    text += " " + " ".join(f"Plain statement number {i} about the world." for i in range(35))
    _, _, m = await doc(session, lambda k: text, "Alpha")
    run = await go(session, m)
    assert run["total"] == 70 and run["uncited_skipped"] == 5 and run["done"] == 40
    only_uncited = " ".join(f"Plain statement number {i} about the world." for i in range(35))
    _, _, m = await doc(session, lambda k: only_uncited, "Alpha")
    assert (await go(session, m))["uncited_skipped"] == 5


async def test_include_uncited_false_leaves_them_out(session):
    _, keys, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m, include_uncited=False)
    assert run["total"] == 4 and run["uncited_skipped"] == 0


async def test_an_overlong_sentence_fails_without_a_model_call(session):
    _, _, m = await doc(session, lambda k: "Word " * 500 + "ends here.", "Alpha")
    await go(session, m)
    [r] = await rows(session, m.id)
    assert (r.status, r.reason) == ("failed", "claim_too_long")


async def test_selection_expands_to_sentences_and_replaces_only_its_rows(session):
    _, keys, m = await doc(session, basic, "Alpha", "Beta")
    await go(session, m)
    await session.execute(update(ManuscriptReviewRun).values(status="done"))
    before = {r.id: r.sentence_hash for r in await rows(session, m.id)}
    text = (await manuscripts.read(session, m.id, "main.tex")).text
    at = text.index("Walking") + 3
    await go(session, m, selection=(at, at + 2))
    after = await rows(session, m.id)
    assert len(after) == 5
    walking = next(r for r in after if r.kind == "uncited")
    assert walking.id not in before and walking.status == "queued"
    assert {r.id for r in after if r.kind == "cited"} == {i for i, h in before.items() if h != walking.sentence_hash}


async def test_full_recheck_drops_stale_rows_and_the_old_run(session):
    _, keys, m = await doc(session, basic, "Alpha", "Beta")
    first = await go(session, m)
    await session.execute(update(ManuscriptReviewRun).values(status="done"))
    await manuscripts.upsert_text(session, m.id, "main.tex", "Only one sentence is left here.")
    await go(session, m, base=FUTURE)
    got = await rows(session, m.id)
    assert [r.kind for r in got] == ["uncited"]
    runs = list(
        await session.scalars(
            select(ManuscriptReviewRun.id)
            .where(ManuscriptReviewRun.manuscript_id == m.id)
            .execution_options(populate_existing=True)
        )
    )
    assert first["id"] not in runs and len(runs) == 1


async def test_refusals_before_any_row(session, local_default_model):
    _, _, m = await doc(session, basic, "Alpha", "Beta")
    with pytest.raises(NotFound, match="unknown_file"):
        await go(session, m, file="nope.tex")
    await manuscripts.upsert_text(session, m.id, "notes.txt", "Plain words only here today.")
    with pytest.raises(InvalidInput, match="not_tex"):
        await go(session, m, file="notes.txt")
    with pytest.raises(Conflict, match="file_changed"):
        await go(session, m, base=datetime(2000, 1, 1, tzinfo=UTC))
    await session.execute(update(type(local_default_model)).values(is_default=False))
    with pytest.raises(Conflict, match="no_model"):
        await go(session, m)
    assert await rows(session, m.id) == []


async def test_a_live_run_refuses_a_second_and_an_old_one_does_not(session):
    _, _, m = await doc(session, basic, "Alpha", "Beta")
    await go(session, m)
    with pytest.raises(Conflict, match="review_running"):
        await go(session, m)
    await session.execute(
        update(ManuscriptReviewRun)
        .where(ManuscriptReviewRun.manuscript_id == m.id)
        .values(updated_at=datetime.now(UTC) - timedelta(minutes=11))
    )
    assert (await mr.state(session, m.id, "main.tex"))["run"]["status"] == "interrupted"
    assert (await go(session, m))["status"] == "queued"


async def test_two_starts_at_once_only_one_runs(monkeypatch):
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)  # its own: the app's pool is tied to a loop
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def resolve(session, model_id):
        return None

    monkeypatch.setattr(mr.llm_connections, "resolve", resolve)
    async with SessionLocal() as s:
        _, _, m = await doc(s, basic, "Alpha", "Beta")
        await s.commit()
        mid = m.id

    async def one():
        async with SessionLocal() as s:
            try:
                return await mr.start(s, mid, file="main.tex", base=FUTURE, selection=None)
            except Conflict as exc:
                return str(exc)

    try:
        outs = await asyncio.gather(one(), one())
        assert sorted(isinstance(o, dict) for o in outs) == [False, True]
        assert "review_running" in outs
    finally:
        async with SessionLocal() as s:
            from app.models import Manuscript, Workspace

            ws = await s.scalar(select(Manuscript.workspace_id).where(Manuscript.id == mid))
            await s.execute(delete(Manuscript).where(Manuscript.id == mid))
            await s.execute(delete(Workspace).where(Workspace.id == ws))
            await s.commit()
        await engine.dispose()


async def test_a_queue_that_is_down_fails_the_run_and_removes_the_rows(session, arq):
    async def down(*a, **k):
        raise ConnectionError("redis is gone")

    arq.enqueue_job = down
    _, _, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m)
    assert (run["status"], run["reason"]) == ("failed", "queue_unavailable")
    assert await rows(session, m.id) == []


async def test_worker_runs_in_order_writes_verdicts_and_finishes(session):
    _, keys, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m)
    seen = []

    class Watching(Scripted):
        async def stream(self, system, prompt):
            seen.append((await mr.state(session, m.id, "main.tex"))["run"]["done"])
            async for x in super().stream(system, prompt):
                yield x

    llm = Watching(check("supported", "x" * 400), check("not_supported"), check("not_addressed"), claim(True))
    await worker.check_manuscript_citations({"llm": llm}, str(run["id"]))
    state = await mr.state(session, m.id, "main.tex")
    assert seen == [1, 2, 3, 4] and (state["run"]["status"], state["run"]["done"]) == ("done", 5)
    verdicts = [(i["cite_key"], i["status"], i["verdict"]) for i in state["items"]]
    assert verdicts == [
        (keys[0], "done", "supported"),
        (keys[0], "done", "not_supported"),
        (keys[1], "done", "not_addressed"),
        ("ghost", "done", "cannot_verify"),
        (None, "done", "claim"),
    ]
    first = state["items"][0]
    assert (
        len(first["reason"]) == 300 and first["model"] == "fake:scripted" and first["paper_title"] in ("Alpha", "Beta")
    )


async def test_one_failure_fails_one_row_only(session):
    _, keys, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m)

    llm = Scripted(RuntimeError("boom"), "not json", "still not json", check("supported"), "garbage", "garbage")
    await worker.check_manuscript_citations({"llm": llm}, str(run["id"]))
    got = [(r.status, r.verdict, r.reason) for r in await rows(session, m.id)]
    assert got[0] == ("failed", None, "check_failed")
    assert got[1] == ("done", "cannot_verify", "model_error")
    assert got[2] == ("done", "supported", "Because.")
    assert got[4] == ("done", "cannot_verify", "model_error")  # an unparsable classify is never a silent not_claim
    run2 = await mr.state(session, m.id, "main.tex")
    assert run2["run"]["status"] == "done"


async def test_a_domain_error_fails_that_row_with_its_code(session):
    _, _, m = await doc(session, lambda k: f"Sleep improves memory consolidation \\cite{{{k[0]}}}.", "Alpha")
    run = await go(session, m)

    class NoModel(Scripted):
        async def stream(self, system, prompt):
            raise Conflict("no_model")
            yield

    await worker.check_manuscript_citations({"llm": NoModel()}, str(run["id"]))
    assert [(r.status, r.reason) for r in await rows(session, m.id)] == [("failed", "no_model")]


async def test_cancel_stops_after_the_row_in_flight(session):
    _, keys, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m)

    class Cancelling(Scripted):
        async def stream(self, system, prompt):
            await mr.cancel(session, m.id, run["id"])
            async for x in super().stream(system, prompt):
                yield x

    await worker.check_manuscript_citations({"llm": Cancelling(check())}, str(run["id"]))
    got = [(r.status, r.reason) for r in await rows(session, m.id)]
    assert got == [
        ("done", "Because."),
        ("failed", "cancelled"),
        ("failed", "cancelled"),
        ("done", "key_not_found"),
        ("failed", "cancelled"),
    ]
    assert (await mr.state(session, m.id, "main.tex"))["run"]["status"] == "cancelled"
    assert (await mr.cancel(session, m.id, run["id"]))["status"] == "cancelled"
    with pytest.raises(NotFound, match="unknown_run"):
        await mr.cancel(session, m.id, uuid.uuid4())


async def test_a_write_with_a_stale_stamp_is_ignored(session):
    _, _, m = await doc(session, lambda k: f"Sleep improves memory consolidation \\cite{{{k[0]}}}.", "Alpha")
    run = await go(session, m)
    row_id, _, _, _, stamp = await worker._take(run["id"])
    await worker._write(run["id"], row_id, stamp + timedelta(seconds=1), status="done", verdict="supported")
    [r] = await rows(session, m.id)
    assert (r.status, r.verdict) == ("running", None)
    assert (await mr.state(session, m.id, "main.tex"))["run"]["done"] == 0
    await worker._write(run["id"], row_id, stamp, status="done", verdict="supported")
    assert (await rows(session, m.id))[0].verdict == "supported"


async def test_an_interrupted_run_reads_so_and_a_new_start_works(session):
    _, _, m = await doc(session, basic, "Alpha", "Beta")
    run = await go(session, m)
    await worker._take(run["id"])
    old = datetime.now(UTC) - timedelta(minutes=11)
    await session.execute(
        update(ManuscriptClaimCheck).where(ManuscriptClaimCheck.manuscript_id == m.id).values(updated_at=old)
    )
    await session.execute(
        update(ManuscriptReviewRun).where(ManuscriptReviewRun.manuscript_id == m.id).values(updated_at=old)
    )
    state = await mr.state(session, m.id, "main.tex")
    assert state["run"]["status"] == "interrupted"
    assert {i["status"] for i in state["items"]} == {"interrupted", "done"}
    assert (await go(session, m))["status"] == "queued"


async def test_dismiss_restore_round_trip_and_survives_a_recheck(session):
    _, _, m = await doc(session, basic, "Alpha", "Beta")
    await mr.dismiss(session, m.id, "abc")
    await mr.dismiss(session, m.id, "abc")
    assert (await mr.state(session, m.id, "main.tex"))["dismissed"] == ["abc"]
    await go(session, m)
    assert (await mr.state(session, m.id, "main.tex"))["dismissed"] == ["abc"]
    await mr.restore(session, m.id, "abc")
    assert (await mr.state(session, m.id, "main.tex"))["dismissed"] == []


async def test_locate_returns_the_spans_and_refuses_huge_text(session):
    text = "Sleep improves memory consolidation \\citep{a,b}. Walking is good for health."
    got = mr.locate(text)
    assert [(s["start"], s["keys"]) for s in got] == [(0, ["a", "b"]), (text.index("Walking"), [])]
    assert text[got[0]["start"] : got[0]["end"]].endswith("\\citep{a,b}.") and len(got[0]["hash"]) == 64
    with pytest.raises(InvalidInput):
        mr.locate("x" * (2 * 1024**2 + 1))


def u16(s: str, i: int) -> int:
    return len(s[:i].encode("utf-16-le")) // 2


MATH = (
    "Let \U0001d53c be the mean \U0001f600 here. "
    "Sleep improves memory consolidation \\citep{a}. Walking is good for health."
)


async def test_locate_speaks_utf16_offsets(session):
    got = mr.locate(MATH)
    assert len(got) == 3
    for s, expected in zip(got, [MATH.index("Let"), MATH.index("Sleep"), MATH.index("Walking")]):
        assert s["start"] == u16(MATH, expected)
    js = MATH.encode("utf-16-le")  # JS slice(start, end) works on these code units
    sliced = [js[2 * s["start"] : 2 * s["end"]].decode("utf-16-le") for s in got]
    assert sliced[1] == "Sleep improves memory consolidation \\citep{a}." and sliced[2] == "Walking is good for health."


async def test_a_selection_in_utf16_offsets_picks_the_right_sentence(session):
    _, _, m = await doc(session, lambda k: MATH, "Alpha")
    at = u16(MATH, MATH.index("Walking")) + 2  # a code-point reading of this would land in the next sentence's end
    await go(session, m, selection=(at, at + 1))
    [r] = await rows(session, m.id)
    assert r.sentence == "Walking is good for health."
    assert mr.from_utf16("a\U0001d53cb", 2) == 1 and mr.from_utf16("a\U0001d53cb", 3) == 2  # inside a pair rounds down


async def test_a_run_with_nothing_to_judge_is_done_and_not_queued(session, arq):
    _, _, m = await doc(session, lambda k: "Word " * 500 + "ends here.", "Alpha")
    assert (await go(session, m))["status"] == "done" and arq.jobs == []


async def test_over_long_uncited_sentences_take_no_classify_slot(session):
    long = "Word " * 500 + "ends here."
    short = " ".join(f"Plain statement number {i} about the world." for i in range(30))
    _, _, m = await doc(session, lambda k: f"{long} {short}", "Alpha")
    run = await go(session, m)
    assert run["uncited_skipped"] == 0 and run["total"] == 31
