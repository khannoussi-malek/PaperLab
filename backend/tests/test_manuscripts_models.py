"""M27a: manuscripts, their files, pinned cite keys and snapshots (migration 0055)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_paper_merges import EVIDENCE, PROOF, kept, merged

from app.core import merges
from app.models import Manuscript, ManuscriptCiteKey, ManuscriptFile, Workspace

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
