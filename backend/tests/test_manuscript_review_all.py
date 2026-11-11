import pytest
from sqlalchemy import delete, select, update
from test_manuscript_review import FUTURE, Scripted, check, claim, rows, wiring  # noqa: F401
from test_manuscript_review import doc as template_doc

from app.core import manuscript_review as mr
from app.core import manuscript_review_all as ra
from app.core import manuscripts
from app.core.errors import Conflict, InvalidInput
from app.models import LLMConnection, LLMModel, ManuscriptFile, ManuscriptReviewRun
from app.workers import manuscript_review as worker

pytestmark = pytest.mark.anyio


async def test_order_follows_inputs_then_the_rest():
    texts = {
        "main.tex": "\\input{sections/a}\n% \\input{sections/skipped}\n\\include{sections/b.tex}\n\\input{nope}",
        "sections/a.tex": "\\input{sections/c}",
        "sections/b.tex": "\\input{main}",  # a cycle
        "sections/c.tex": "",
        "sections/skipped.tex": "",
        "zz.tex": "",
        "appendix.tex": "",
    }
    assert ra.tex_order(texts, "main.tex") == [
        "main.tex",
        "sections/a.tex",
        "sections/c.tex",
        "sections/b.tex",
        "appendix.tex",
        "sections/skipped.tex",
        "zz.tex",
    ]


async def test_order_without_the_main_file_is_by_path():
    assert ra.tex_order({"b.tex": "", "a.tex": ""}, "main.tex") == ["a.tex", "b.tex"]


async def doc(session, text_fn, *titles):
    """A bare manuscript: the article template's section files are removed, so only the files a test names exist."""
    papers, keys, m = await template_doc(session, text_fn, *titles)
    await session.execute(
        delete(ManuscriptFile).where(ManuscriptFile.manuscript_id == m.id, ManuscriptFile.path.like("sections/%"))
    )
    await session.flush()
    return papers, keys, m


def cites(n, key):
    return " ".join(f"Claim number {i} is well established \\cite{{{key}}}." for i in range(n))


async def two_files(session, a=2, b=1):
    papers, keys, m = await doc(
        session, lambda k: f"\\input{{sections/b}} {cites(a, k[0])} Walking is good for health.", "Alpha"
    )
    await manuscripts.upsert_text(
        session, m.id, "sections/b.tex", cites(b, keys[0]) + " This ghost claim cites nothing \\cite{ghost}."
    )
    return keys, m


async def test_estimate_counts_pairs_per_file_and_writes_nothing(session):
    keys, m = await two_files(session)
    est = await ra.estimate(session, m.id, include_uncited=True)
    assert [(f["path"], f["pairs"], f["uncited"]) for f in est["files"]] == [
        ("main.tex", 2, 1),
        ("sections/b.tex", 1, 0),
    ]
    assert (est["pairs"], est["uncited"], est["needs_confirm"]) == (3, 1, False)
    assert await rows(session, m.id) == []
    assert (await ra.estimate(session, m.id, include_uncited=False))["uncited"] == 0


async def test_no_tex_file_is_refused(session):
    papers, keys, m = await doc(session, lambda k: "x", "Alpha")
    # manuscripts.remove() refuses the main file (Conflict main_file), so delete the rows directly
    await session.execute(
        delete(ManuscriptFile).where(ManuscriptFile.manuscript_id == m.id, ManuscriptFile.path.like("%.tex"))
    )
    await session.flush()
    with pytest.raises(InvalidInput, match="no_tex"):
        await ra.estimate(session, m.id, include_uncited=True)
    with pytest.raises(InvalidInput, match="no_tex"):
        await ra.start_all(session, m.id)


async def test_start_all_writes_rows_for_every_file_in_order(session, arq):
    keys, m = await two_files(session)
    run = await ra.start_all(session, m.id)
    assert run["file"] == "*" and run["total"] == 5
    got = await rows(session, m.id)
    # main first (cited, cited, uncited), then b (cited, ghost)
    assert [r.file_path for r in got] == ["main.tex"] * 3 + ["sections/b.tex"] * 2
    assert [r.ord for r in got] == [0, 1, 2, 3, 4]
    assert arq.jobs == [("check_manuscript_citations", str(run["id"]))]


async def test_same_sentence_in_two_files_is_two_rows_and_a_restart_replaces_everything(session, arq):
    papers, keys, m = await doc(session, lambda k: cites(1, k[0]), "Alpha")
    await manuscripts.upsert_text(session, m.id, "sections/b.tex", cites(1, keys[0]))
    first = await ra.start_all(session, m.id, include_uncited=False)
    assert len(await rows(session, m.id)) == 2
    await session.execute(
        ManuscriptReviewRun.__table__.update().where(ManuscriptReviewRun.id == first["id"]).values(status="done")
    )
    second = await ra.start_all(session, m.id, include_uncited=False)
    assert second["id"] != first["id"] and len(await rows(session, m.id)) == 2
    assert (
        len(list(await session.scalars(select(ManuscriptReviewRun).where(ManuscriptReviewRun.manuscript_id == m.id))))
        == 1
    )


async def test_big_runs_need_confirm_large_and_over_600_refuse(session, arq):
    papers, keys, m = await doc(session, lambda k: cites(20, k[0]), "Alpha")
    await manuscripts.upsert_text(session, m.id, "sections/b.tex", cites(11, keys[0]))  # 31 pairs
    with pytest.raises(InvalidInput, match="confirm_large") as exc:
        await ra.start_all(session, m.id)
    assert exc.value.details["count"] == 31 and await rows(session, m.id) == [] and arq.jobs == []
    assert (await ra.start_all(session, m.id, confirm_large=True))["total"] >= 31
    papers, keys, big = await doc(session, lambda k: cites(601, k[0]), "Alpha")
    with pytest.raises(InvalidInput, match="too_many_claims"):
        await ra.start_all(session, big.id, confirm_large=True)
    assert await rows(session, big.id) == []


async def test_a_live_run_refuses_a_second_start(session, arq):
    keys, m = await two_files(session)
    await ra.start_all(session, m.id)
    with pytest.raises(Conflict, match="review_running"):
        await ra.start_all(session, m.id)


async def test_remote_default_needs_confirm_remote(session, arq):
    keys, m = await two_files(session)
    # the setup of `_remote` in tests/test_remote_confirm.py: a cloud connection made the default model
    await session.execute(update(LLMModel).values(is_default=False))
    c = LLMConnection(kind="openai_compatible", label="Cloud", base_url="https://api.example.com/v1")
    session.add(c)
    await session.flush()
    session.add(LLMModel(connection_id=c.id, name="big", is_default=True))
    await session.flush()
    with pytest.raises(Conflict, match="remote_model_needs_confirm"):
        await ra.start_all(session, m.id)
    assert await rows(session, m.id) == [] and arq.jobs == []
    assert (await ra.start_all(session, m.id, confirm_remote=True))["file"] == "*"


async def test_the_job_judges_both_files_and_cancel_stops_it(session, arq):
    keys, m = await two_files(session, a=1, b=1)
    run = await ra.start_all(session, m.id, include_uncited=False)
    await worker.check_manuscript_citations({"llm": Scripted(check(), check())}, str(run["id"]))
    got = await rows(session, m.id)
    assert [(r.file_path, r.status) for r in got] == [
        ("main.tex", "done"),
        ("sections/b.tex", "done"),
        ("sections/b.tex", "done"),
    ]
    keys, m2 = await two_files(session, a=2, b=0)
    run2 = await ra.start_all(session, m2.id, include_uncited=False)
    await mr.cancel(session, m2.id, run2["id"])
    await worker.check_manuscript_citations({"llm": Scripted()}, str(run2["id"]))
    assert {r.reason for r in await rows(session, m2.id) if r.status == "failed"} == {"cancelled"}
