import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_DATABASE_URL
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_manuscript_papers import setup

from app.core import manuscript_papers, manuscripts, queue
from app.core import manuscript_section_review as msr
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import ManuscriptSectionReview as Row
from app.models import Note, note_anchors, note_papers
from app.providers.base import LLMError, LLMUnavailable
from app.workers import manuscript_section_review as worker

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("manuscript_rows")]  # flips the default model
FUTURE = datetime.now(UTC) + timedelta(days=1)
GOOD = (
    "Missing: no sample size is named\n"
    "Unsupported: the memory claim has no figure behind it [S1]\n"
    "Supported: the aim is stated [S1] and noted [N1]\n"
)
SAMPLE = (
    "\\section{Introduction}\nSleep improves memory in adults \\citep{KEY}. Many people sleep eight hours.\n"
    "\\section{Methods}\nWe measured sleep for ten nights. We recruited forty adults.\n"
    "\\section*{Acknowledgements}\nThanks to all of the people.\n"
    "\\section{A Weird Title}\nSome words here to read.\n"
)


class Scripted:
    model, connection_name = "fake:scripted", "Test"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    async def stream(self, system, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield reply


@pytest.fixture(autouse=True)
def wiring(session, arq, monkeypatch, local_default_model):
    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(queue, "_pool", arq)
    monkeypatch.setattr(worker, "SessionLocal", shared_session)


async def doc(session, text=SAMPLE, *titles):
    _, papers, m = await setup(session, *(titles or ("Alpha",)), name=f"W {uuid.uuid4().hex[:8]}")
    listed = await manuscript_papers.list_papers(session, m.id)  # unordered: pick the first paper made
    key = next(p["key"] for p in listed if p["paper_id"] == papers[0].id)
    await manuscripts.upsert_text(session, m.id, "main.tex", text.replace("KEY", key))
    return papers, m


async def note(session, paper, body, provenance="human", page=None, age=0):
    n = Note(
        body=body, provenance=provenance, created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=age)
    )
    session.add(n)
    await session.flush()
    await session.execute(insert(note_papers).values(note_id=n.id, paper_id=paper.id))
    if page:
        await session.execute(
            insert(note_anchors).values(
                note_id=n.id, paper_id=paper.id, page=page, bbox=[[1, 2, 3, 4]], quoted_text="q"
            )
        )
    return n


async def go(session, m, **kw):
    kw = {"file": "main.tex", "base": FUTURE, "at": 5, "role": None, "confirm_remote": False} | kw
    return await msr.start(session, m.id, **kw)


async def rows(session, mid):
    return list(
        await session.scalars(
            select(Row).where(Row.manuscript_id == mid).order_by(Row.title).execution_options(populate_existing=True)
        )
    )


async def test_start_stores_source_numbered_inputs_and_only_human_notes(session, arq):
    papers, m = await doc(session)
    await note(session, papers[0], "my own idea", "human", page=3)
    await note(session, papers[0], "the model wrote this", "llm")
    await note(session, papers[0], "model text I edited", "llm_edited")
    out = await go(session, m)
    (row,) = await rows(session, m.id)
    assert (out["status"], out["role"], out["role_source"], out["title"]) == (
        "queued",
        "intro",
        "guessed",
        "Introduction",
    )
    assert row.source.startswith("\\section{Introduction}") and "Methods" not in row.source
    assert row.inputs["sentences"][0].startswith("Sleep improves memory in adults")
    assert row.inputs["notes"] == ["my own idea"]
    assert row.inputs["note_meta"][0]["label"] == "Jane Smith 2021 p.3"
    assert arq.jobs == [("review_manuscript_section", str(row.id))]
    assert out["ai"] is True and out["findings"] == []


async def test_notes_cap_at_twelve_cited_papers_first_cut_to_400(session):
    papers, m = await doc(session, SAMPLE, "Alpha", "Beta")
    other = papers[1]
    for i in range(10):
        await note(session, other, "other " + "x" * 500, age=i)
    cited = [await note(session, papers[0], f"cited {i}", age=100 + i) for i in range(5)]
    await go(session, m)
    (row,) = await rows(session, m.id)
    notes = row.inputs["notes"]
    assert len(notes) == 12 and all(len(n) <= 400 for n in notes)
    assert notes[:5] == [f"cited {i}" for i in range(5)] and [x["note_id"] for x in row.inputs["note_meta"][:5]] == [
        str(n.id) for n in cited
    ]


async def test_role_guess_chosen_override_and_the_prompt_holds_only_that_rubric(session):
    papers, m = await doc(session)
    at = (await manuscripts.get_text(session, m.id, "main.tex")).index("We measured")
    out = await go(session, m, at=at, role="results")  # inside Methods
    assert (out["role"], out["role_source"], out["title"]) == ("results", "chosen", "Methods")
    llm = Scripted(GOOD)
    await worker.review_manuscript_section({"llm": llm}, str(out["id"]))
    from app.core.section_rubrics import rubric_for

    assert all(i.text in llm.prompts[0] for i in rubric_for("results"))
    assert not any(i.text in llm.prompts[0] for i in rubric_for("intro"))


@pytest.mark.parametrize("at,role", [(210, None), (270, None), (5, "other"), (5, "back"), (5, "bogus")])
async def test_unknown_role_writes_nothing_and_never_calls_the_model(session, arq, at, role):
    papers, m = await doc(session)
    text = await manuscripts.get_text(session, m.id, "main.tex")
    at = text.index("Thanks") if at == 210 else text.index("Some words") if at == 270 else at
    with pytest.raises(InvalidInput, match="unknown_role"):
        await go(session, m, at=at, role=role)
    assert await rows(session, m.id) == [] and arq.jobs == []


async def test_section_too_long_by_chars_and_by_sentences(session):
    _, m = await doc(session, "\\section{Introduction}\n" + "word " * 12_001 + ".\n")
    with pytest.raises(InvalidInput, match="section_too_long"):
        await go(session, m)
    _, m = await doc(session, "\\section{Introduction}\n" + "Sleep improves memory in adults. " * 151 + "\n")
    with pytest.raises(InvalidInput, match="section_too_long"):
        await go(session, m)


async def test_no_section_file_changed_no_model_and_remote_confirm(session, arq):
    _, m = await doc(session, "Front matter words.\n" + SAMPLE)
    with pytest.raises(InvalidInput, match="no_section"):
        await go(session, m, at=3)
    with pytest.raises(Conflict, match="file_changed"):
        await go(session, m, base=datetime(2000, 1, 1, tzinfo=UTC))
    with pytest.raises(NotFound, match="unknown_file"):
        await go(session, m, file="nope.tex")
    assert arq.jobs == [] and await rows(session, m.id) == []


async def test_not_tex_and_no_model(session):
    from sqlalchemy import update as upd

    from app.models import LLMModel

    _, m = await doc(session)
    await manuscripts.upsert_text(session, m.id, "refs.bib", "@article{a}")
    with pytest.raises(InvalidInput, match="not_tex"):
        await go(session, m, file="refs.bib")
    await session.execute(upd(LLMModel).values(is_default=False))
    with pytest.raises(Conflict, match="no_model"):
        await go(session, m)
    assert await rows(session, m.id) == []


async def test_worker_writes_findings_refs_and_dropped(session):
    papers, m = await doc(session)
    n = await note(session, papers[0], "my idea", page=2)
    out = await go(session, m)
    reply = GOOD + "Missing: rewrite it as: Sleep is vital\n"
    await worker.review_manuscript_section({"llm": Scripted(reply)}, str(out["id"]))
    (row,) = await rows(session, m.id)
    assert (row.status, row.dropped, row.model) == ("done", 1, "fake:scripted")
    refs = [r for f in row.findings for r in f["refs"]]
    s = next(r for r in refs if r["kind"] == "sentence")
    assert s["n"] == 1 and s["hash"] and "Sleep improves memory in adults".startswith(s["preview"][:20])
    assert s["preview"] in row.inputs["sentences"][0]
    note_ref = next(r for r in refs if r["kind"] == "note")
    assert (note_ref["note_id"], note_ref["label"]) == (str(n.id), "Jane Smith 2021 p.2")
    got = (await msr.state(session, m.id, "main.tex"))["reviews"][0]
    assert got["status"] == "done" and got["dropped"] == 1 and len(got["findings"]) == 3


async def test_a_bad_reply_twice_is_model_error_and_model_failures_are_plain(session):
    for replies, reason in [
        (["nothing useful", "still nothing"], "model_error"),
        ([LLMError("boom")], "model_error"),
        ([LLMUnavailable("down")], "model_unavailable"),
    ]:
        papers, m = await doc(session)
        out = await go(session, m)
        await worker.review_manuscript_section({"llm": Scripted(*replies)}, str(out["id"]))
        (row,) = await rows(session, m.id)
        assert (row.status, row.reason) == ("failed", reason)


async def test_an_unexpected_error_is_check_failed(session):
    papers, m = await doc(session)
    out = await go(session, m)
    await worker.review_manuscript_section({"llm": Scripted(RuntimeError("bug"))}, str(out["id"]))
    assert (await rows(session, m.id))[0].reason == "check_failed"


async def test_cancel_then_a_late_write_is_ignored(session):
    papers, m = await doc(session)
    out = await go(session, m)
    taken = await worker._take(out["id"])
    stamp = taken[-1] if isinstance(taken, tuple) else taken
    cancelled = await msr.cancel(session, m.id, out["id"])
    assert (cancelled["status"], cancelled["reason"]) == ("failed", "cancelled")
    await worker._write(out["id"], stamp, status="done", findings=[], dropped=0, model="x")
    (row,) = await rows(session, m.id)
    assert (row.status, row.reason) == ("failed", "cancelled")
    await msr.cancel(session, m.id, out["id"])  # a finished row stays as it is
    with pytest.raises(NotFound):
        await msr.cancel(session, m.id, uuid.uuid4())


async def test_an_edit_between_start_and_write_finishes_with_the_old_hash(session):
    papers, m = await doc(session)
    out = await go(session, m)
    edited = SAMPLE.replace("Sleep improves", "Rest improves").replace("KEY", "x")
    await manuscripts.upsert_text(session, m.id, "main.tex", edited)
    await worker.review_manuscript_section({"llm": Scripted(GOOD)}, str(out["id"]))
    (row,) = await rows(session, m.id)
    assert row.status == "done"
    spans = msr.locate("main.tex", edited, "main.tex")
    assert row.section_hash not in {s["hash"] for s in spans}
    listed = (await msr.state(session, m.id, "main.tex"))["reviews"]
    assert [r["section_hash"] for r in listed] == [row.section_hash]  # still shown, stale on first read


async def test_a_redo_replaces_only_its_own_row_and_stale_hash_rows_go(session):
    papers, m = await doc(session)
    intro = await go(session, m)
    methods_at = (await manuscripts.get_text(session, m.id, "main.tex")).index("We measured")
    await session.execute(update(Row).where(Row.id == intro["id"]).values(status="done"))
    methods = await go(session, m, at=methods_at)
    await session.execute(update(Row).where(Row.id == methods["id"]).values(status="done"))
    again = await go(session, m)  # redo Introduction: only its row is replaced
    got = {r.title: r for r in await rows(session, m.id)}
    assert set(got) == {"Introduction", "Methods"} and got["Introduction"].id == again["id"]
    assert got["Methods"].id == methods["id"]
    await session.execute(update(Row).where(Row.id == again["id"]).values(status="done"))
    current = await manuscripts.get_text(session, m.id, "main.tex")
    await manuscripts.upsert_text(session, m.id, "main.tex", current.replace("ten nights", "ten days"))
    await go(session, m, at=current.index("We measured") + 2)  # redo edited Methods; its old (stale hash) row goes
    assert {r.title for r in await rows(session, m.id)} == {"Introduction", "Methods"}
    assert len(await rows(session, m.id)) == 2


async def test_a_live_row_blocks_a_start_and_an_old_one_reads_interrupted(session):
    papers, m = await doc(session)
    out = await go(session, m)
    with pytest.raises(Conflict, match="review_running"):
        await go(session, m)
    await session.execute(
        update(Row).where(Row.id == out["id"]).values(updated_at=datetime.now(UTC) - timedelta(minutes=21))
    )
    assert (await msr.state(session, m.id, "main.tex"))["reviews"][0]["status"] == "interrupted"
    assert (await go(session, m))["status"] == "queued"


async def test_two_starts_at_once_only_one_runs(monkeypatch):
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    Local = async_sessionmaker(engine, expire_on_commit=False)

    async def allow(session, confirmed):
        return None

    monkeypatch.setattr(msr.llm_connections, "refuse_unconfirmed_remote", allow)
    async with Local() as s:
        _, m = await doc(s)
        await s.commit()
        mid = m.id

    async def one():
        async with Local() as s:
            try:
                return await msr.start(s, mid, file="main.tex", base=FUTURE, at=5, role=None, confirm_remote=False)
            except Conflict as exc:
                return str(exc)

    try:
        outs = await asyncio.gather(one(), one())
        assert sorted(isinstance(o, dict) for o in outs) == [False, True] and "review_running" in outs
    finally:
        async with Local() as s:
            from app.models import Manuscript, Paper, Workspace

            ws = await s.scalar(select(Manuscript.workspace_id).where(Manuscript.id == mid))
            await s.execute(delete(Manuscript).where(Manuscript.id == mid))
            await s.execute(delete(Workspace).where(Workspace.id == ws))
            await s.execute(delete(Paper).where(Paper.title == "Alpha", Paper.file_path == "/x.pdf"))
            await s.commit()
        await engine.dispose()


async def test_a_queue_that_is_down_fails_the_row(session, monkeypatch):
    async def down(*a, **k):
        raise ConnectionError("redis is gone")

    monkeypatch.setattr(queue, "enqueue", down)
    papers, m = await doc(session)
    out = await go(session, m)
    assert (out["status"], out["reason"]) == ("failed", "queue_unavailable")


SLICE_TEXT = (
    "\\section{Introduction}\n\U0001f600 Sleep improves memory in adults. Many people sleep eight hours.\n"
    "\\section{Methods}\nWe measured sleep for ten nights.\n"
)


async def test_locate_pins_utf16_offsets_for_the_fixture_slices():
    spans = msr.locate("main.tex", SLICE_TEXT, "main.tex")
    assert [(s["title"], s["start"], s["end"], s["guess"]) for s in spans] == [
        ("Introduction", 0, 90, "intro"),
        ("Methods", 90, 90 + len(SLICE_TEXT) - 89, "method"),
    ]
    assert SLICE_TEXT[89:].startswith("\\section{Methods}")  # code points: one fewer than UTF-16 units
    assert set(spans[0]) == {"title", "start", "end", "hash", "words", "guess"}


async def test_locate_pins_the_sample_fixture_offsets():
    from pathlib import Path

    sample = (Path(__file__).parent / "fixtures" / "section_sample.tex").read_text()
    spans = msr.locate("main.tex", sample, "main.tex")
    assert [(s["title"], s["start"], s["end"]) for s in spans] == [
        ("Introduction", 103, 300),
        ("Methods", 300, 348),
        ("Results and Findings", 348, 413),
        ("A Weird Title", 413, 454),
        ("Acknowledgements", 454, 497),
    ]


async def test_locate_of_a_main_with_inputs_has_no_spans_and_a_huge_text_refuses():
    main = "\\begin{document}\n\\input{sections/a}\n\\end{document}\n"
    assert msr.locate("main.tex", main, "main.tex") == []
    with pytest.raises(InvalidInput, match="text_too_long"):
        msr.locate("main.tex", "x" * (3 * 1024**2), "main.tex")


async def test_job_timeout_is_under_the_live_window():
    from app.workers.manuscript_section_review import SECTION_REVIEW_JOB_TIMEOUT

    assert SECTION_REVIEW_JOB_TIMEOUT < msr.LIVE.total_seconds()
