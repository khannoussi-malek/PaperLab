"""M40 Task 3: the export carries every field Zotero takes (abstract, page range, identifiers, keywords)."""

import datetime
import uuid
from types import SimpleNamespace

import bibtexparser
import pytest
import rispy

from app.core import citations_export, tags, workspaces
from app.core.citations_export import csl_item, render
from app.models import Paper
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

RUN = uuid.uuid4().hex[:8]


def paper(**kw):
    base = dict(
        id=uuid.uuid4(), title="A study of things", authors=["Jane Smith"], year=2020, venue="Journal of Things",
        doi="10.1234/abc", source_type="journal_article", peer_reviewed="true", evidence_access="full_text",
        published_doi=None, published_venue=None, oa_url=None, abstract="We study things.", issn="1234-5678",
        volume="12", issue="3", pages="45-67", editors=None, pmid="123456", pmcid="PMC789",
    )  # fmt: skip
    return SimpleNamespace(**{**base, **kw})


def test_csl_item_carries_the_new_fields():
    item = csl_item(paper(oa_url="https://example.org/p.pdf"))
    assert item["abstract"] == "We study things." and item["ISSN"] == "1234-5678"
    assert item["URL"] == "https://example.org/p.pdf" and item["DOI"] == "10.1234/abc"
    assert (item["volume"], item["issue"], item["page"]) == ("12", "3", "45-67")
    assert (item["PMID"], item["PMCID"]) == ("123456", "PMC789")
    assert item["keyword"] == "journal article, peer-reviewed"


def test_keywords_put_the_workspace_tags_first_and_skip_unknown_review():
    item = csl_item(paper(peer_reviewed="unknown", source_type="preprint"), keywords=["rq1", "include"])
    assert item["keyword"] == "rq1, include, preprint"


def test_extra_lines_name_arxiv_pubmed_and_the_published_version():
    item = csl_item(
        paper(source_type="preprint", doi="10.48550/arXiv.2401.00001", published_doi="10.1/x", published_venue="Nature")
    )
    lines = item["note"].split("\n")
    assert "arXiv: 2401.00001" in lines and "PMID: 123456" in lines and "PMCID: PMC789" in lines
    assert "Published version: Nature https://doi.org/10.1/x" in lines
    assert item["type"] == "article" and item["DOI"] == "10.48550/arXiv.2401.00001"
    assert not any(line.startswith("arXiv") for line in csl_item(paper())["note"].split("\n"))


def test_bibtex_has_every_field_and_round_trips():
    arxiv = paper(source_type="preprint", doi="10.48550/arXiv.2401.00001", title="Pre", venue=None, pages=None)
    text = render([csl_item(paper(), keywords=["rq1"]), csl_item(arxiv)], "bibtex")
    by_title = {e["title"]: e for e in bibtexparser.parse_string(text).entries}
    e = by_title["A study of things"]
    assert e["abstract"] == "We study things." and e["issn"] == "1234-5678"
    assert (e["volume"], e["number"], e["pages"]) == ("12", "3", "45--67")
    assert (e["pmid"], e["pmcid"]) == ("123456", "PMC789")
    assert e["keywords"] == "rq1, journal article, peer-reviewed"
    p = by_title["Pre"]
    assert (p["eprint"], p["archivePrefix"]) == ("2401.00001", "arXiv")
    assert "eprint" not in e.fields_dict


def test_ris_has_every_field_and_round_trips():
    arxiv = paper(source_type="preprint", doi="10.48550/arXiv.2401.00001", title="Pre", venue=None)
    entries = rispy.loads(render([csl_item(paper(), keywords=["rq1"]), csl_item(arxiv)], "ris"))
    e = entries[0]
    assert e["abstract"] == "We study things." and e["issn"] == "1234-5678"
    assert (e["volume"], e["number"], e["start_page"], e["end_page"]) == ("12", "3", "45", "67")
    assert e["keywords"] == ["rq1", "journal article", "peer-reviewed"]
    assert "PMID: 123456" in e["notes"] and "PMCID: PMC789" in e["notes"]
    assert "arXiv: 2401.00001" in entries[1]["notes"]


def test_apa_shows_volume_issue_and_an_en_dash_page_range():
    assert "12(3), 45–67" in render([csl_item(paper())], "apa")


def test_apa_html_italicises_the_volume_like_apa():
    assert "<i>12</i>(3), 45–67" in render([csl_item(paper())], "apa-html")


pytestmark_db = [pytest.mark.anyio, pytest.mark.xdist_group("references")]


@pytest.mark.anyio
@pytest.mark.xdist_group("references")
async def test_workspace_export_adds_its_tags_and_screening_decision(session):
    ws = (await workspaces.create(session, f"Kw {RUN}")).id
    other = (await workspaces.create(session, f"Kw other {RUN}")).id
    p = Paper(title=f"Kw paper {RUN}", file_path="/x.pdf", page_count=1, authors=["Jane Smith"], year=2021,
              source_type="journal_article")  # fmt: skip
    session.add(p)
    await session.commit()
    for w in (ws, other):
        await workspaces.add_paper(session, w, p.id)
    await tags.tag_papers(session, ws, "RQ1", [p.id])
    await tags.tag_papers(session, other, "elsewhere", [p.id])
    run = WorkspaceSearchRun(
        workspace_id=ws,
        query_text="q",
        sources_json=[],
        status="exhausted",
        started_at=datetime.datetime.now(datetime.UTC),
    )
    session.add(run)
    await session.commit()
    session.add(WorkspaceSearchHit(
        workspace_id=ws, run_id=run.id, source_method="database_search", normalized_title="kw",
        first_seen_at=datetime.datetime.now(datetime.UTC), stage1_status="relevant", paper_id=p.id,
    ))  # fmt: skip
    await session.commit()
    text, _ = await citations_export.export_papers(session, workspace_id=ws, fmt="bibtex")
    entry = bibtexparser.parse_string(text).entries[0]
    assert entry["keywords"] == "RQ1, screening: relevant, journal article"
    lib, _ = await citations_export.export_papers(session, paper_ids=[p.id], fmt="bibtex")
    assert bibtexparser.parse_string(lib).entries[0]["keywords"] == "journal article"
    # a tag-filtered selection inside a workspace keeps that workspace's keywords
    sel, _ = await citations_export.export_papers(session, workspace_id=ws, paper_ids=[p.id], fmt="bibtex")
    assert "RQ1" in bibtexparser.parse_string(sel).entries[0]["keywords"]
