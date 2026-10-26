import pytest
from sqlalchemy import select

from app.core import manuscripts, workspaces
from app.core.citations_export import _bibtex, bibtex_keys, csl_item
from app.core.manuscript_bib import build_bib, cited_keys
from app.models import ManuscriptCiteKey, Paper, Workspace

pytestmark = pytest.mark.anyio


async def setup(session, *titles, with_ws=True):
    ws = Workspace(name="W")
    session.add(ws)
    await session.flush()
    papers = []
    for title in titles:
        p = Paper(title=title, file_path="/x.pdf", authors=["Jane Smith"], year=2021)
        session.add(p)
        await session.flush()
        await workspaces.add_paper(session, ws.id, p.id)
        papers.append(p)
    m = await manuscripts.create(session, title="M", template="article", workspace_id=ws.id if with_ws else None)
    return ws, papers, m


async def pins(session, m):
    return {
        r.key: r.paper_id
        for r in await session.scalars(select(ManuscriptCiteKey).where(ManuscriptCiteKey.manuscript_id == m.id))
    }


def test_cited_keys_reads_every_command_form_and_skips_comments():
    src = (
        "\\cite{a} \\citep[see][p. 3]{b, c} \\citet*{d}\\citealp{e}\\citeauthor{f}\\citeyear{g}\\nocite{h,a}\n"
        "% \\cite{hidden}\n"
        "text 50\\% \\cite{i} % \\cite{gone}\n"
    )
    assert cited_keys([src]) == list("abcdefghi")


def test_bibtex_keys_without_pinned_is_unchanged():
    p = [csl_item(_P("1", "Deep one")), csl_item(_P("2", "Deep two"))]
    assert bibtex_keys(p) == {"1": "smith2021deepa", "2": "smith2021deepb"}
    assert bibtex_keys(p, {"2": "smith2021deepa"}) == {"2": "smith2021deepa", "1": "smith2021deepb"}
    assert _bibtex(p).startswith("@misc{smith2021deepa,")


class _P:
    def __init__(self, id, title):
        self.id, self.title, self.authors, self.year = id, title, ["Jane Smith"], 2021
        self.source_type = self.venue = self.doi = self.oa_url = self.peer_reviewed = self.evidence_access = None


async def test_a_cited_key_is_pinned_on_build(session):
    _, (p,), m = await setup(session, "Deep learning")
    bib = await build_bib(session, m, {"main.tex": "\\cite{smith2021deep} \\cite{nobody}"})
    assert "@misc{smith2021deep," in bib
    assert await pins(session, m) == {"smith2021deep": p.id}


async def test_a_colliding_new_paper_does_not_move_a_pinned_key(session):
    ws, (p,), m = await setup(session, "Deep learning")
    await build_bib(session, m, {"main.tex": "\\cite{smith2021deep}"})
    q = Paper(title="Deep a", file_path="/x.pdf", authors=["Jane Smith"], year=2021)
    session.add(q)
    await session.flush()
    await workspaces.add_paper(session, ws.id, q.id)
    bib = await build_bib(session, m, {})
    assert await pins(session, m) == {"smith2021deep": p.id}
    assert "@misc{smith2021deep," in bib and "Deep learning" in bib.split("smith2021deep,")[1].split("@")[0]
    assert "smith2021deepa," in bib


async def test_deleted_paper_keeps_its_stored_entry(session):
    ws, (p,), m = await setup(session, "Deep learning")
    await build_bib(session, m, {"main.tex": "\\cite{smith2021deep}"})
    await workspaces.remove_paper(session, ws.id, p.id)
    await session.delete(p)
    await session.flush()
    bib = await build_bib(session, m, {})
    assert "@misc{smith2021deep," in bib and "Deep learning" in bib


async def test_orphan_manuscript_bib_holds_only_pinned_keys(session):
    _, _, m = await setup(session, with_ws=False)
    assert await build_bib(session, m, {"main.tex": "\\cite{smith2021deep}"}) == ""
