"""M27a: manuscripts, their files, pinned cite keys and snapshots (migration 0055)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_paper_merges import EVIDENCE, PROOF, kept, merged

from app.core import merges
from app.models import (
    Manuscript,
    ManuscriptCiteKey,
    ManuscriptClaimCheck,
    ManuscriptClaimDismissal,
    ManuscriptEvidence,
    ManuscriptFile,
    ManuscriptReviewRun,
    ManuscriptSnapshot,
    Workspace,
)

pytestmark = pytest.mark.anyio


async def manuscript(session, **fields) -> Manuscript:
    m = Manuscript(title="Draft", **fields)
    session.add(m)
    await session.flush()
    return m


async def test_deleting_a_workspace_keeps_its_manuscript_with_no_workspace(session):
    ws = Workspace(name="Writing")
    session.add(ws)
    await session.flush()
    m = await manuscript(session, workspace_id=ws.id)
    await session.flush()
    assert (m.main_file, m.compile_status, m.compile_requested) == ("main.tex", "never", False)
    await session.execute(text("DELETE FROM workspaces WHERE id = :w"), {"w": ws.id})
    await session.refresh(m)
    assert m.workspace_id is None


async def test_a_file_must_be_text_or_data_not_both(session):
    m = await manuscript(session)
    for fields in ({"text": "a", "data": b"a"}, {}):
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(ManuscriptFile(manuscript_id=m.id, path="x.tex", size=1, **fields))
                await session.flush()


async def test_paths_are_unique_per_manuscript(session):
    m = await manuscript(session)
    session.add(ManuscriptFile(manuscript_id=m.id, path="main.tex", text="a", size=1))
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(ManuscriptFile(manuscript_id=m.id, path="main.tex", data=b"b", size=1))
            await session.flush()


async def test_merge_moves_a_pinned_key_to_the_kept_paper(session):
    k, m = await kept(session), await merged(session)
    ms = await manuscript(session)
    session.add(ManuscriptCiteKey(manuscript_id=ms.id, key="sleep2021", paper_id=m.id, bibtex="@article{sleep2021}"))
    await session.commit()
    await merges.merge(session, m.id, k.id, identifier=PROOF, evidence=EVIDENCE)
    key = await session.scalar(
        select(ManuscriptCiteKey).where(ManuscriptCiteKey.key == "sleep2021").execution_options(populate_existing=True)
    )
    assert key.paper_id == k.id


async def test_a_snapshot_may_have_the_before_sections_reason(session):
    m = await manuscript(session)
    session.add(ManuscriptSnapshot(manuscript_id=m.id, reason="before_sections", files={}))
    await session.flush()


async def test_a_snapshot_may_have_the_before_mcp_reason_but_no_unknown_one(session):
    m = await manuscript(session)
    session.add(ManuscriptSnapshot(manuscript_id=m.id, reason="before_mcp", files={}))
    await session.flush()
    session.add(ManuscriptSnapshot(manuscript_id=m.id, reason="before_nothing", files={}))
    with pytest.raises(IntegrityError):
        await session.flush()


def evidence(ms, paper, **fields) -> ManuscriptEvidence:
    return ManuscriptEvidence(
        manuscript_id=ms.id, sentence_hash="h", sentence="Sleep helps.", paper_id=paper.id, rank=0, **fields
    )


async def test_evidence_starts_queued_with_no_verdict(session):
    ms, p = await manuscript(session), await kept(session)
    row = evidence(ms, p, status="queued")
    session.add(row)
    await session.flush()
    await session.refresh(row)
    assert (row.verdict, row.reason, row.quote, row.page, row.output_id) == (None,) * 5
    assert row.created_at and row.updated_at


async def test_evidence_status_must_be_a_known_one(session):
    ms, p = await manuscript(session), await kept(session)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(evidence(ms, p, status="interrupted"))
            await session.flush()


async def test_one_evidence_row_per_sentence_and_paper(session):
    ms, p = await manuscript(session), await kept(session)
    session.add(evidence(ms, p, status="queued"))
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(evidence(ms, p, status="done"))
            await session.flush()


async def test_deleting_a_paper_deletes_its_evidence_and_a_manuscript_its_own(session):
    ms, p = await manuscript(session), await kept(session)
    session.add(evidence(ms, p, status="done"))
    await session.commit()
    count = "SELECT count(*) FROM manuscript_evidence WHERE manuscript_id = :m"
    await session.execute(text("DELETE FROM papers WHERE id = :p"), {"p": p.id})
    assert await session.scalar(text(count), {"m": ms.id}) == 0
    q = await kept(session, doi="10.1/other")
    session.add(evidence(ms, q, status="done"))
    await session.flush()
    await session.execute(text("DELETE FROM manuscripts WHERE id = :m"), {"m": ms.id})
    assert await session.scalar(text(count), {"m": ms.id}) == 0
    await session.execute(text("DELETE FROM papers WHERE id = :p"), {"p": q.id})
    await session.commit()


async def test_a_deleted_output_leaves_the_evidence_row(session):
    ms, p = await manuscript(session), await kept(session)
    paper_id = p.id
    out = await session.scalar(text(
        "INSERT INTO llm_outputs (paper_id, kind, content, model, prompt_version) "
        "VALUES (:p, 'chat', 'A', 'f', 1) RETURNING id"), {"p": p.id})  # fmt: skip
    row = evidence(ms, p, status="done", output_id=out)
    session.add(row)
    await session.flush()
    row_id = row.id
    await session.execute(text("DELETE FROM llm_outputs WHERE id = :o"), {"o": out})
    left = await session.scalar(text("SELECT output_id FROM manuscript_evidence WHERE id = :i"), {"i": row_id})
    assert left is None
    await session.rollback()
    await session.execute(text("DELETE FROM papers WHERE id = :p"), {"p": paper_id})
    await session.commit()


async def test_merge_repoints_evidence_and_drops_the_duplicate(session):
    k, m = await kept(session), await merged(session)
    ms = await manuscript(session)
    for h in ("a", "b"):
        session.add(ManuscriptEvidence(
            manuscript_id=ms.id, sentence_hash=h, sentence="S.", paper_id=m.id, rank=0, status="done"
        ))  # fmt: skip
    session.add(ManuscriptEvidence(
        manuscript_id=ms.id, sentence_hash="a", sentence="S.", paper_id=k.id, rank=0, status="queued"
    ))  # fmt: skip
    await session.commit()
    await merges.merge(session, m.id, k.id, identifier=PROOF, evidence=EVIDENCE)
    rows = await session.execute(
        text("SELECT sentence_hash, paper_id, status FROM manuscript_evidence WHERE manuscript_id = :m ORDER BY 1"),
        {"m": ms.id},
    )
    assert rows.all() == [("a", k.id, "queued"), ("b", k.id, "done")]


def run_of(ms, **fields) -> ManuscriptReviewRun:
    return ManuscriptReviewRun(
        manuscript_id=ms.id, file_path="main.tex", status="queued", total=3, include_uncited=False, **fields
    )


def check(ms, paper=None, **fields) -> ManuscriptClaimCheck:
    kind = "cited" if paper or fields.get("cite_key") else "uncited"
    fields = {"kind": kind, "status": "queued", "sentence_hash": "h"} | fields
    if paper:
        fields = {"cite_key": "k"} | fields
    return ManuscriptClaimCheck(
        manuscript_id=ms.id, file_path="main.tex", sentence="Sleep helps.", plain="Sleep helps.", ord=0,
        paper_id=paper.id if paper else None, **fields,
    )  # fmt: skip


async def rejects(session, row) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(row)
            await session.flush()


async def test_a_run_starts_with_zero_done_skipped_and_no_cancel(session):
    ms = await manuscript(session)
    run = run_of(ms)
    session.add(run)
    await session.flush()
    await session.refresh(run)
    assert (run.done, run.uncited_skipped, run.cancel_requested, run.reason) == (0, 0, False, None)
    assert run.created_at and run.updated_at
    bad = ManuscriptReviewRun(manuscript_id=ms.id, file_path="m", status="paused", total=1, include_uncited=True)
    await rejects(session, bad)


async def test_check_kind_and_status_must_be_known_ones(session):
    ms, p = await manuscript(session), await kept(session)
    await rejects(session, check(ms, p, kind="maybe"))
    await rejects(session, check(ms, p, status="cancelled"))


async def test_one_check_per_sentence_and_paper_but_cited_and_uncited_coexist(session):
    ms, p = await manuscript(session), await kept(session)
    session.add_all([check(ms, p), check(ms, None)])
    await session.flush()
    await rejects(session, check(ms, p, cite_key="other"))
    await rejects(session, check(ms, None))
    q = await kept(session, doi="10.1/other")
    session.add(check(ms, q))  # another paper for the same sentence is fine
    await session.flush()


async def test_deleting_a_paper_deletes_its_checks_and_a_run_keeps_its_rows(session):
    ms, p, q = await manuscript(session), await kept(session), await kept(session, doi="10.1/other")
    run = run_of(ms)
    session.add(run)
    await session.flush()
    session.add_all([check(ms, p, run_id=run.id), check(ms, q, run_id=run.id, sentence_hash="g")])
    await session.flush()
    await session.execute(text("DELETE FROM papers WHERE id = :p"), {"p": p.id})
    await session.execute(text("DELETE FROM manuscript_review_runs WHERE id = :r"), {"r": run.id})
    rows = await session.execute(text("SELECT paper_id, run_id FROM manuscript_claim_checks WHERE manuscript_id = :m"),
                                 {"m": ms.id})  # fmt: skip
    assert rows.all() == [(q.id, None)]
    await session.rollback()  # nothing to clean up: the papers and manuscript were never committed


async def test_one_sentence_holds_several_unresolved_keys_but_each_once(session):
    ms = await manuscript(session)
    session.add_all([check(ms, cite_key="x"), check(ms, cite_key="y"), check(ms, None)])
    await session.flush()
    await rejects(session, check(ms, cite_key="x"))
    await rejects(session, check(ms, None))  # still one uncited row per sentence


async def test_an_uncited_row_has_no_paper_or_key_and_a_cited_one_has_a_key(session):
    ms, p = await manuscript(session), await kept(session)
    await rejects(session, check(ms, p, kind="uncited"))
    await rejects(session, check(ms, None, kind="uncited", cite_key="x"))
    await rejects(session, check(ms, None, kind="cited"))
    await rejects(session, check(ms, p, cite_key=None))


async def test_deleting_the_manuscript_removes_runs_checks_and_dismissals(session):
    ms = await manuscript(session)
    session.add_all([run_of(ms), check(ms, None), ManuscriptClaimDismissal(manuscript_id=ms.id, sentence_hash="h")])
    await session.flush()
    await session.execute(text("DELETE FROM manuscripts WHERE id = :m"), {"m": ms.id})
    for table in ("manuscript_review_runs", "manuscript_claim_checks", "manuscript_claim_dismissals"):
        assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE manuscript_id = :m"), {"m": ms.id}) == 0  # noqa: S608


async def test_a_sentence_is_dismissed_once(session):
    ms = await manuscript(session)
    session.add(ManuscriptClaimDismissal(manuscript_id=ms.id, sentence_hash="h"))
    await session.flush()
    await rejects(session, ManuscriptClaimDismissal(manuscript_id=ms.id, sentence_hash="h"))


async def test_merge_repoints_checks_and_drops_the_duplicate(session):
    k, m = await kept(session), await merged(session)
    ms = await manuscript(session)
    session.add_all([
        check(ms, m, sentence_hash="a", status="done", cite_key="m"),
        check(ms, m, sentence_hash="b", status="done", cite_key="m"),
        check(ms, k, sentence_hash="a", cite_key="k"),  # a different key for the same sentence still collides
        check(ms, None, sentence_hash="a"),
    ])  # fmt: skip
    await session.commit()
    await merges.merge(session, m.id, k.id, identifier=PROOF, evidence=EVIDENCE)
    rows = await session.execute(
        text("SELECT sentence_hash, paper_id, status FROM manuscript_claim_checks WHERE manuscript_id = :m "
             "ORDER BY 1, 2 NULLS LAST"), {"m": ms.id})  # fmt: skip
    assert rows.all() == [("a", k.id, "queued"), ("a", None, "queued"), ("b", k.id, "done")]


async def test_merge_moves_a_cited_row_when_k_holds_only_an_uncited_one(session):
    k, m = await kept(session), await merged(session)
    ms = await manuscript(session)
    session.add_all([check(ms, m, status="done"), check(ms, None), check(ms, None, cite_key="gone", sentence_hash="u")])
    await session.commit()
    await merges.merge(session, m.id, k.id, identifier=PROOF, evidence=EVIDENCE)
    rows = await session.execute(
        text("SELECT paper_id, kind FROM manuscript_claim_checks WHERE manuscript_id = :m ORDER BY 2, 1 NULLS LAST"),
        {"m": ms.id},
    )
    assert rows.all() == [(k.id, "cited"), (None, "cited"), (None, "uncited")]
