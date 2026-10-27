"""M27a: manuscripts, their files, pinned cite keys and snapshots (migration 0055)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_paper_merges import EVIDENCE, PROOF, kept, merged

from app.core import merges
from app.models import Manuscript, ManuscriptCiteKey, ManuscriptEvidence, ManuscriptFile, ManuscriptSnapshot, Workspace

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
