import pytest
from sqlalchemy import delete
from test_manuscript_papers import setup

from app.core import manuscript_papers as mp
from app.core import manuscripts
from app.core.errors import NotFound
from app.core.manuscript_missing_keys import missing_keys as all_missing
from app.models import ManuscriptFile, Paper

pytestmark = pytest.mark.anyio


async def missing_keys(session, mid):
    # the template's own sections cite a few keys too; these tests look at main.tex only
    return [r for r in await all_missing(session, mid) if r["file"] == "main.tex"]


async def put(session, m, path, text):
    await manuscripts.upsert_text(session, m.id, path, text)


async def test_unknown_key_listed_with_file_and_line(session):
    _, _, m = await setup(session, "Deep learning")
    await put(session, m, "main.tex", "Hi.\nSee \\cite{nowhere}.\n")
    assert await missing_keys(session, m.id) == [{"key": "nowhere", "file": "main.tex", "line": 2}]


async def test_library_pinned_orphan_pin_and_own_bib_keys_are_known(session):
    _, papers, m = await setup(session, "Deep learning", "Other work")
    lib = next(r["key"] for r in await mp.list_papers(session, m.id) if str(r["paper_id"]) == str(papers[0].id))
    pinned = await mp.pin(session, m.id, papers[1].id)
    await session.execute(delete(Paper).where(Paper.id == papers[1].id))
    await put(session, m, "refs.bib", '@comment{ghost, x}\n  @article{mine,\n title={T}}\n@string{s = "x"}\n')
    await put(session, m, "main.tex", f"\\cite{{{lib}}} \\cite{{{pinned}}} \\cite{{mine}} \\cite{{ghost}} \\cite{{s}}")
    assert [r["key"] for r in await missing_keys(session, m.id)] == ["ghost", "s"]


async def test_commented_cite_ignored_and_multiline_uses_command_line(session):
    _, _, m = await setup(session, "Deep learning")
    await put(session, m, "main.tex", "% \\cite{hidden}\nx\n\\cite{a,\n b}\n")
    assert await missing_keys(session, m.id) == [
        {"key": "a", "file": "main.tex", "line": 3},
        {"key": "b", "file": "main.tex", "line": 3},
    ]


async def test_no_workspace_lists_every_non_bib_key(session):
    _, _, m = await setup(session, with_ws=False)
    await put(session, m, "refs.bib", "@book{mine, title={T}}\n")
    await put(session, m, "main.tex", "\\cite{mine,other}")
    assert [r["key"] for r in await missing_keys(session, m.id)] == ["other"]


async def test_paperlab_bib_entries_do_not_count(session):
    _, _, m = await setup(session, with_ws=False)
    text = "@article{fake, title={T}}\n"
    session.add(ManuscriptFile(manuscript_id=m.id, path="paperlab.bib", text=text, size=len(text)))
    await session.flush()
    await put(session, m, "main.tex", "\\cite{fake}")
    assert [r["key"] for r in await missing_keys(session, m.id)] == ["fake"]


async def test_unknown_manuscript_raises(session):
    import uuid

    with pytest.raises(NotFound):
        await all_missing(session, uuid.uuid4())


async def test_route(client, session):
    _, _, m = await setup(session, "Deep learning")
    await put(session, m, "main.tex", "\\cite{nowhere}")
    await session.commit()
    r = await client.get(f"/api/manuscripts/{m.id}/missing-keys")
    assert r.status_code == 200 and {"key": "nowhere", "file": "main.tex", "line": 1} in r.json()
    import uuid

    assert (await client.get(f"/api/manuscripts/{uuid.uuid4()}/missing-keys")).status_code == 404
