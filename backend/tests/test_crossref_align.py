"""Year, venue and pages corrected from Crossref for a paper with a DOI: the issue year, the journal's name at the
time and the full page range (a researcher's paperlab.bib against the published records)."""

import uuid
from contextlib import asynccontextmanager

import pytest

from app.core import enrichment
from app.models import Paper
from app.scripts import backfill_biblio
from tests.test_enrichment import add_paper, hints
from tests.test_source_enrichment import fake_crossref

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

DOI = "10.1126/sciadv.adn5290"
FULL = {"volume": "10", "issue": "28", "pages": "289", "editors": ["E"], "pmid": "1", "pmcid": "PMC1"}


def crossref_work(**extra):
    return {
        "type": "journal-article",
        "issued": {"date-parts": [[2023, 7, 12]]},
        "published-print": {"date-parts": [[2024, 7]]},
        "container-title": ["Journal of Secondary Gifted Education"],
        "page": "289-297",
        **extra,
    }


def paper_like(**fields):
    return Paper(**{"title": "t", "doi": DOI, "manual_fields": [], **fields})


def test_a_print_year_later_than_openalex_s_is_taken():
    assert enrichment.align_with_crossref(paper_like(year=2023), crossref_work())["year"] == 2024


def test_issued_is_used_when_there_is_no_print_date():
    work = crossref_work(**{"published-print": None, "issued": {"date-parts": [[2021]]}})
    assert enrichment.align_with_crossref(paper_like(year=2023), work)["year"] == 2021


def test_a_manual_year_or_venue_is_kept():
    paper = paper_like(year=2023, venue="Journal of Advanced Academics", manual_fields=["year", "venue"])
    fixes = enrichment.align_with_crossref(paper, crossref_work())
    assert "year" not in fixes and "venue" not in fixes


@pytest.mark.parametrize("copy", [{"doi": "10.48550/arxiv.2301.00001"}, {"source_type": "preprint"}])
def test_a_preprint_copy_keeps_its_own_details(copy):
    paper = paper_like(**{"year": 2023, "venue": "arXiv", "pages": "289", **copy})
    assert enrichment.align_with_crossref(paper, crossref_work()) == {}


def test_container_title_replaces_the_journal_s_current_name():
    paper = paper_like(year=2024, venue="Journal of Advanced Academics")
    fixes = enrichment.align_with_crossref(paper, crossref_work())
    assert fixes["venue"] == "Journal of Secondary Gifted Education"
    work = crossref_work(**{"container-title": ["Proceedings of the 16th Conference on Creativity &amp; Cognition"]})
    assert enrichment.align_with_crossref(paper, work)["venue"] == (
        "Proceedings of the 16th Conference on Creativity & Cognition"
    )


def test_a_lone_first_page_becomes_the_range_but_another_page_does_not():
    assert enrichment.align_with_crossref(paper_like(pages="289"), crossref_work())["pages"] == "289-297"
    assert "pages" not in enrichment.align_with_crossref(paper_like(pages="290"), crossref_work())
    assert "pages" not in enrichment.align_with_crossref(paper_like(pages="289-300"), crossref_work())


async def test_ingest_aligns_from_the_crossref_fetch_it_already_made(session, fake_openalex):
    fake_openalex.route(
        f"/works/doi:{DOI}",
        {
            "id": "https://openalex.org/W9990077",
            "doi": f"https://doi.org/{DOI}",
            "title": "Align test",
            "publication_year": 2023,
            "type": "article",
            "primary_location": {"source": {"display_name": "Journal of Advanced Academics"}},
            "biblio": {"volume": "10", "issue": "28", "first_page": "289", "last_page": None},
        },
    )
    fake_openalex.route("/authors", {"results": []})
    paper = await add_paper(session, doi=DOI, manual_fields=["doi"])
    client, seen = fake_crossref(crossref_work())
    await enrichment.enrich_paper(session, fake_openalex.client, paper.id, hints(), crossref_http=client)
    await session.refresh(paper)
    assert (paper.year, paper.venue, paper.pages) == (2024, "Journal of Secondary Gifted Education", "289-297")
    assert paper.field_sources["bibliographic"] == "crossref"
    assert [r.url.path for r in seen] == [f"/works/{DOI}"]


async def test_backfill_align_selects_full_papers_and_corrects_them(session):
    full = await add_paper(session, doi=f"10.9999/align-{uuid.uuid4().hex[:8]}", year=2023, **FULL)
    client, _ = fake_crossref(crossref_work())
    assert (await backfill_biblio.run(session, client, None, delay=0, only=[full.id]))["checked"] == 0
    summary = await backfill_biblio.run(session, client, None, delay=0, only=[full.id], align=True)
    await session.refresh(full)
    assert summary == {"checked": 1, "updated": 1}
    assert (full.year, full.venue, full.pages) == (2024, "Journal of Secondary Gifted Education", "289-297")


async def test_backfill_align_dry_run_counts_full_papers_and_asks_nobody(session, monkeypatch, capsys):
    await add_paper(session, doi=f"10.9999/align-{uuid.uuid4().hex[:8]}", **FULL)

    @asynccontextmanager
    async def this_session():
        yield session

    monkeypatch.setattr(backfill_biblio, "SessionLocal", this_session)
    monkeypatch.setattr(backfill_biblio.crossref, "new_client", lambda **k: pytest.fail("built a client"))
    monkeypatch.setattr(backfill_biblio.openalex, "new_client", lambda **k: pytest.fail("built a client"))
    counts = []
    for align in (False, True):
        await backfill_biblio.main(dry_run=True, align=align)
        counts.append(int(capsys.readouterr().out.split("would check ")[1].split()[0]))
    assert counts[1] > counts[0]
