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


def test_cited_keys_reads_natbib_and_biblatex_commands():
    src = (
        "\\citealt{a} \\citenum{b} \\citeyearpar[p.~2]{c} \\Citet{d} \\Citep*[see][]{e} \\Citealp{f}\n"
        "\\parencite{g} \\textcite[ch.~3]{h} \\autocite{i} \\Parencite{j} \\footcite{k} \\citeauthor*{l}\n"
        "% \\textcite{hidden}\n"
        "\\recite{m} \\excite{n}\n"  # any letters around "cite": a custom \\recite resolves as BibTeX sees it
    )
    assert cited_keys([src]) == list("abcdefghijklmn")


ORIGINAL_F7 = (
    "@article{smith2021deepa,\n\tauthor = {Smith, Jane},\n\ttitle = {Deep learning},\n"
    "\tjournal = {Journal of Things},\n\tyear = {2021},\n"
    "\tnote = {Source: journal article \u00b7 peer-reviewed \u00b7 full text in PaperLab},\n"
    "\tkeywords = {journal article, peer-reviewed},\n\tdoi = {10.1/x}\n}\n\n\n"
    "@article{smith2021deepb,\n\tauthor = {Smith, Jane},\n\ttitle = {Deep nets},\n"
    "\tjournal = {Journal of Things},\n\tyear = {2021},\n"
    "\tnote = {Source: journal article \u00b7 peer-reviewed \u00b7 full text in PaperLab},\n"
    "\tkeywords = {journal article, peer-reviewed}\n}\n\n\n"
    "@article{wei2019graphs,\n\tauthor = {Wei, Li},\n\ttitle = {Graphs},\n"
    "\tjournal = {Journal of Things},\n\tyear = {2019},\n"
    "\tnote = {Source: journal article \u00b7 peer-reviewed \u00b7 full text in PaperLab},\n"
    "\tkeywords = {journal article, peer-reviewed}\n}\n"
)  # captured from citations_export.py at e28daef, before `pinned` existed


class _P:
    def __init__(self, id, title, authors=("Jane Smith",), year=2021, **kw):
        self.id, self.title, self.authors, self.year = id, title, list(authors), year
        self.source_type, self.venue, self.peer_reviewed = "journal_article", "Journal of Things", "true"
        self.doi = self.oa_url = None
        self.evidence_access = "full_text"
        self.__dict__.update(kw)


def test_bibtex_without_pinned_is_byte_identical_to_the_original():
    items = [
        csl_item(_P("1", "Deep learning", doi="10.1/x")),
        csl_item(_P("2", "Deep nets")),
        csl_item(_P("3", "Graphs", ["Li Wei"], 2019)),
    ]
    assert _bibtex(items) == ORIGINAL_F7


def test_keys_do_not_depend_on_input_order():
    items = [csl_item(_P(str(i), t)) for i, t in enumerate(["Deep one", "Deep two", "Deepa", "Other"])]
    assert bibtex_keys(items) == bibtex_keys(items[::-1]) == bibtex_keys(items[2:] + items[:2])


def test_a_base_key_that_equals_another_groups_suffixed_key_gets_a_distinct_key():
    items = [csl_item(_P("1", "Deep one")), csl_item(_P("2", "Deep two")), csl_item(_P("3", "Deepa"))]
    keys = bibtex_keys(items)
    assert keys == {"1": "smith2021deepa", "2": "smith2021deepb", "3": "smith2021deepaa"}
    assert len(set(keys.values())) == 3


def test_a_lone_paper_whose_key_is_pinned_elsewhere_takes_the_next_free_letter():
    items = [csl_item(_P("1", "Deep one"))]
    assert bibtex_keys(items, {"gone": "smith2021deep"}) == {"1": "smith2021deepa"}


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


async def test_merging_two_papers_pinned_in_one_manuscript_keeps_both_keys(session):
    import re

    from test_paper_merges import EVIDENCE, PROOF, kept, merged

    from app.core import merges

    k, m = await kept(session), await merged(session)
    ws = Workspace(name="W")
    session.add(ws)
    await session.flush()
    for p in (k, m):
        await workspaces.add_paper(session, ws.id, p.id)
    draft = await manuscripts.create(session, title="M", template="article", workspace_id=ws.id)
    keys = re.findall(r"@\w+\{([^,]+),", await build_bib(session, draft, {}))
    source = {"main.tex": "".join(f"\\cite{{{key}}}" for key in keys)}
    await build_bib(session, draft, source)
    draft_id, k_id = draft.id, k.id
    await session.commit()
    assert len(keys) == 2

    result = await merges.merge(session, m.id, k_id, identifier=PROOF, evidence=EVIDENCE)
    assert result.status == "merged"

    draft = await manuscripts.get(session, draft_id)
    bib = await build_bib(session, draft, source)
    assert sorted(re.findall(r"@\w+\{([^,]+),", bib)) == sorted(keys)  # each \cite still resolves, once
    assert await pins(session, draft) == {key: k_id for key in keys}


async def test_a_paper_that_left_the_workspace_keeps_its_stored_entry(session):
    ws, (p,), m = await setup(session, "Deep learning")
    await build_bib(session, m, {"main.tex": "\\cite{smith2021deep}"})
    await workspaces.remove_paper(session, ws.id, p.id)
    bib = await build_bib(session, m, {})
    assert "@misc{smith2021deep," in bib


async def test_a_manuscript_bib_carries_publishing_fields_only(session):
    ws, (p,), m = await setup(session, "Praise and creativity")
    p.venue, p.volume, p.issue, p.pages = "Creativity Research Journal", "18", "3", "385-388"
    p.doi, p.peer_reviewed, p.abstract = "10.1207/s15326934crj1803_13", "true", "Long."  # library notes would follow
    await session.flush()
    bib = await build_bib(session, m, {"main.tex": "\\cite{smith2021praise}"})
    assert "@article{smith2021praise," in bib and "journal = {Creativity Research Journal}" in bib
    assert "volume = {18}" in bib and "pages = {385--388}" in bib and "doi = {10.1207/s15326934crj1803_13}" in bib
    for leak in ("in PaperLab", "peer-reviewed", "Source:", "keywords", "abstract", "annote"):
        assert leak not in bib, leak


async def test_a_preprint_keeps_its_genre_note_in_a_manuscript_bib(session):
    ws, (p,), m = await setup(session, "Large models")
    p.source_type = "preprint"
    await session.flush()
    bib = await build_bib(session, m, {})
    assert "note = {Preprint}" in bib and "in PaperLab" not in bib


def test_the_library_export_still_carries_paperlabs_notes():
    from types import SimpleNamespace

    paper = SimpleNamespace(
        id="p1", title="T", authors=["Jane Smith"], year=2020, venue="J", doi=None, source_type="journal_article",
        peer_reviewed="true", evidence_access="abstract", published_doi=None, oa_url=None,
    )
    assert "abstract only in PaperLab" in _bibtex([csl_item(paper)])
