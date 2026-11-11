import pytest
from sqlalchemy import delete, update
from test_manuscript_review import FUTURE, rows, wiring  # noqa: F401
from test_manuscript_review import doc as template_doc

from app.core import manuscript_review as mr
from app.core import manuscript_review_all as ra
from app.core import manuscript_review_report as rep
from app.core import manuscripts
from app.core.errors import NotFound
from app.models import ManuscriptFile, ManuscriptReviewRun

pytestmark = pytest.mark.anyio


async def doc(session, text_fn, *titles):
    """A bare manuscript: the article template's section files are removed, so only the files a test names exist."""
    papers, keys, m = await template_doc(session, text_fn, *titles)
    await session.execute(
        delete(ManuscriptFile).where(ManuscriptFile.manuscript_id == m.id, ManuscriptFile.path.like("sections/%"))
    )
    await session.flush()
    return papers, keys, m


async def finished(session):
    papers, keys, m = await doc(
        session,
        lambda k: (
            f"One thing is claimed \\cite{{{k[0]}}}. "
            f"Another thing is claimed \\cite{{{k[0]}}}. Plain words are written here."
        ),
        "Alpha",
    )
    await ra.start_all(session, m.id)
    a, b, c = await rows(session, m.id)
    a.status, a.verdict, a.reason, a.quote, a.page = "done", "supported", "Matches.", "the quote", 3
    b.status, b.verdict, b.reason = "done", "not_supported", "It says the opposite."
    c.status, c.verdict = "done", "claim"
    await session.flush()
    return m


async def test_report_groups_counts_and_orders(session):
    m = await finished(session)
    r = await rep.build(session, m.id)
    assert [f["path"] for f in r["files"]] == ["main.tex"]
    assert r["counts"] == {"supported": 1, "not_supported": 1, "claim": 1}
    first = r["files"][0]["items"][0]
    assert (first["outcome"], first["quote"], first["page"], first["paper_title"]) == (
        "supported",
        "the quote",
        3,
        "Alpha",
    )


async def test_dismissed_sentences_are_left_out_and_counted(session):
    m = await finished(session)
    h = (await rows(session, m.id))[2].sentence_hash
    await mr.dismiss(session, m.id, h)
    r = await rep.build(session, m.id)
    assert r["dismissed"] == 1 and "claim" not in r["counts"]


async def test_unfinished_rows_count_as_unfinished(session):
    m = await finished(session)
    (await rows(session, m.id))[0].status = "failed"
    await session.flush()
    assert (await rep.build(session, m.id))["counts"]["unfinished"] == 1


async def test_report_reads_only_the_latest_runs_rows(session, arq):
    papers, keys, m = await doc(session, lambda k: f"One thing is claimed \\cite{{{k[0]}}}.", "Alpha")
    await manuscripts.upsert_text(session, m.id, "sections/b.tex", f"Other thing is claimed \\cite{{{keys[0]}}}.")
    await ra.start_all(session, m.id, include_uncited=False)
    for r in await rows(session, m.id):
        r.status, r.verdict = "done", "supported"
    await session.execute(update(ManuscriptReviewRun).values(status="done"))
    await session.flush()
    await mr.start(session, m.id, file="main.tex", base=FUTURE, selection=None, include_uncited=False)  # a per-file run
    r = await rep.build(session, m.id)
    assert r["run"]["file"] == "main.tex"
    assert [f["path"] for f in r["files"]] == ["main.tex"] and sum(
        r["counts"].values()
    ) == 1  # b.tex's old row is left out


async def test_no_run_is_unknown_run(session):
    papers, keys, m = await doc(session, lambda k: "x", "Alpha")
    with pytest.raises(NotFound, match="unknown_run"):
        await rep.build(session, m.id)


async def test_markdown_lists_problems_first_with_quotes_and_pages(session):
    md = rep.render_markdown(await rep.build(session, (await finished(session)).id))
    assert md.startswith("# Citation review")
    assert "| Contradicted | 1 |" in md and "| Supported | 1 |" in md
    assert md.index("Contradicted**") < md.index("Supported**")
    assert "the quote (p. 3)" in md and "It says the opposite." in md
    assert "Rewrite" not in md and "Suggest" not in md  # D118: no wording
