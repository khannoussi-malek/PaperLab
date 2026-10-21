"""R22: papers.field_sources names the source that last filled each group of a paper's details. Every writer stamps
the groups it actually wrote; a field the guard drops claims nothing; a hand edit is told by manual_fields instead."""

import uuid

import pytest
from conftest import recorded
from sqlalchemy import update

from app.core import citations_import_apply, discovery, enrichment, paper_enrichment, papers, provenance
from app.core.candidates import Candidate
from app.core.citations_import import ImportEntry
from app.models import Paper
from tests.test_enrichment import BERT_DOI, BERT_WORK, add_paper, hints
from tests.test_paper_biblio import CROSSREF, DOI, openalex_work
from tests.test_paper_enrichment import EMNLP, arxiv_paper, library, run
from tests.test_source_enrichment import fake_crossref

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

PDF = b"%PDF-1.7\nbody"


def test_groups_follow_r22():
    assert provenance.groups_of(["title", "pmid", "pages", "abstract", "peer_reviewed", "published_venue"]) == {
        "bibliographic", "identifiers", "citation", "abstract", "source_type", "published",
    }  # fmt: skip
    assert provenance.groups_of(["oa_url", "is_retracted"]) == set()


def test_a_blank_value_claims_nothing_and_an_unknown_source_is_refused():
    assert provenance.sources_of({"title": "T", "abstract": None, "editors": []}, "crossref") == {
        "bibliographic": "crossref"
    }
    with pytest.raises(ValueError):
        provenance.sources_of({"title": "T"}, "google")


async def test_an_openalex_match_stamps_its_groups(session, fake_openalex):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})
    paper = await add_paper(session)
    await enrichment.enrich_paper(session, fake_openalex.client, paper.id, hints(doi=BERT_DOI))
    await session.refresh(paper)
    groups = ("bibliographic", "identifiers", "abstract", "source_type")
    assert {g: paper.field_sources.get(g) for g in groups} == dict.fromkeys(groups, "openalex")


async def test_the_pdf_hints_stamp_pdf_when_openalex_has_nothing(session):
    paper = await add_paper(session)
    await enrichment.enrich_paper(session, None, paper.id, hints(doi="10.9999/prov.hint", authors=["Ada Lovelace"]))
    await session.refresh(paper)
    assert paper.field_sources == {"bibliographic": "pdf", "identifiers": "pdf"}


async def test_crossref_stamps_the_citation_and_its_type(session):
    paper = await add_paper(session, doi=DOI)
    client, _ = fake_crossref(CROSSREF)
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    await session.refresh(paper)
    assert paper.field_sources == {"citation": "crossref", "source_type": "crossref"}


async def test_biblio_stamps_each_group_with_the_source_that_filled_it(session):
    paper = await add_paper(session, doi=DOI)
    client, _ = fake_crossref(CROSSREF)
    await enrichment.fill_biblio(session, paper.id, client, openalex_work=openalex_work())
    await session.refresh(paper)
    assert (paper.volume, paper.pmid) == ("12", "12345")  # Crossref wins the citation; OpenAlex gives the ids
    assert paper.field_sources == {"citation": "crossref", "identifiers": "openalex"}


async def test_a_citation_both_sources_filled_reads_crossref(session):
    paper = await add_paper(session, doi=DOI)
    client, _ = fake_crossref({"type": "journal-article", "page": "45-67"})  # Crossref has the pages only
    only_volume = openalex_work(biblio={"volume": "7"}, ids={})  # OpenAlex has the volume only
    await enrichment.fill_biblio(session, paper.id, client, openalex_work=only_volume)
    await session.refresh(paper)
    assert (paper.volume, paper.pages) == ("7", "45-67")
    assert paper.field_sources == {"citation": "crossref"}  # Crossref wins the group it shares with OpenAlex


async def test_biblio_claims_only_the_groups_whose_nulls_it_filled(session):
    held = {"volume": "1", "issue": "2", "pages": "3", "editors": ["E"]}
    paper = await add_paper(session, doi=DOI, **held, field_sources={"citation": "zotero"})
    await enrichment.fill_biblio(session, paper.id, None, openalex_work=openalex_work())
    await session.refresh(paper)
    assert paper.field_sources == {"citation": "zotero", "identifiers": "openalex"}


async def test_semantic_scholar_stamps_the_published_version(session):
    p = arxiv_paper()
    ws = await library(session, p)
    await run(session, ws, [EMNLP])
    await session.refresh(p)
    assert p.field_sources == {"published": "semantic_scholar", "source_type": "semantic_scholar"}


async def test_an_openalex_published_version_stamps_openalex(session):
    p = arxiv_paper()
    session.add(p)
    await session.flush()
    await session.refresh(p)
    work = {
        "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1000/prov.pub", "type": "article",
        "primary_location": {"source": {"display_name": "Journal", "type": "journal"}},
    }  # fmt: skip
    assert paper_enrichment.apply_openalex(p, work)
    await session.commit()
    await session.refresh(p)
    assert p.field_sources == {"published": "openalex", "source_type": "openalex"}


async def test_a_candidate_prefill_stamps_the_candidate_source(session, tmp_path):
    found = Candidate("Found", ["A B"], 2020, "V", doi="10.9999/prov.c", abstract="Abs", sources=("crossref",))
    paper = await papers.create_paper(session, "f.pdf", PDF, tmp_path, prefill=discovery.prefill(found))
    assert paper.field_sources == {"bibliographic": "crossref", "identifiers": "crossref", "abstract": "crossref"}
    elsewhere = Candidate("Elsewhere", sources=("dblp", "openalex"))  # the first one that is a details source
    assert discovery.prefill(elsewhere)["field_sources"] == {"bibliographic": "openalex"}
    unknown = Candidate("Unknown", sources=("dblp",))
    assert discovery.prefill(unknown)["field_sources"] == {"bibliographic": "search"}


async def test_a_metadata_paper_stamps_its_details_source(session):
    prefill = discovery.prefill(Candidate("No PDF", abstract="Abs", sources=("crossref",)))
    paper = await papers.create_metadata_paper(session, prefill, details_source="semantic_scholar")
    assert paper.field_sources == {"bibliographic": "semantic_scholar", "abstract": "semantic_scholar"}


async def test_a_zotero_entry_stamps_zotero(session, tmp_path):
    entry = ImportEntry("Zotero paper", doi="10.9999/prov.z", volume="3", source_type="journal_article")
    prefill = citations_import_apply._prefill(entry)
    paper = await papers.create_paper(session, "z.pdf", PDF, tmp_path, prefill=prefill)
    assert paper.field_sources == dict.fromkeys(("bibliographic", "identifiers", "citation", "source_type"), "zotero")


async def test_a_zotero_fill_claims_only_what_was_missing(session):
    paper = await add_paper(session, volume="9", field_sources={"citation": "crossref"})
    entry = ImportEntry("Zotero paper", volume="3", abstract="From Zotero")
    await citations_import_apply._fill_from_entry(session, paper.id, entry)
    await session.refresh(paper)
    assert (paper.volume, paper.abstract) == ("9", "From Zotero")
    assert paper.field_sources == {"citation": "crossref", "abstract": "zotero"}


async def test_a_field_the_guard_drops_claims_nothing(session):
    holder = await add_paper(session, title="Holder", doi="10.9999/prov.taken")
    paper = await add_paper(session, authors=["Known"], year=2019, abstract="Mine", manual_fields=["abstract"])
    # manual: the abstract; regressions: blanks over the known byline and year; taken: the DOI
    fields = {"abstract": "Theirs", "authors": [], "year": None, "doi": holder.doi, "published_doi": "10.9/p"}
    collisions = await enrichment._write(session, paper, fields, "openalex")
    await session.commit()
    await session.refresh(paper)
    assert [c.column for c in collisions] == ["doi"]
    assert (paper.abstract, paper.authors, paper.year, paper.doi) == ("Mine", ["Known"], 2019, None)
    assert paper.field_sources == {"published": "openalex"}  # only the field that was written


async def test_a_hand_correction_stamps_its_groups_as_yours(session):
    """manual_fields also holds locks the app sets itself (a search result's title and DOI), so "edited by you" can't
    be read from it: a correction records itself, including a field cleared to blank."""
    paper = await add_paper(session, field_sources={"bibliographic": "openalex", "citation": "crossref"})
    await enrichment.correct_metadata(session, paper.id, {"title": "Mine", "volume": None})
    await session.refresh(paper)
    assert paper.field_sources == {"bibliographic": "manual", "citation": "manual"}
    assert {"title", "volume"} <= set(paper.manual_fields)


async def test_paper_out_carries_field_sources_and_manual_fields(client, session):
    created = (await client.post("/api/papers", files={"file": ("p.pdf", PDF, "application/pdf")})).json()
    assert (created["field_sources"], created["manual_fields"]) == ({}, [])
    assert (created["pdf_checked_at"], created["pdf_check_result"]) == (None, None)
    stamped = {"field_sources": {"abstract": "pdf"}, "manual_fields": ["title"], "pdf_check_result": "none"}
    await session.execute(update(Paper).where(Paper.id == uuid.UUID(created["id"])).values(**stamped))
    body = (await client.get(f"/api/papers/{created['id']}")).json()
    assert {k: body[k] for k in stamped} == stamped
