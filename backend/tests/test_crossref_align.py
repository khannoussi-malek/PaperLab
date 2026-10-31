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


async def full_paper(session, **fields):
    doi = f"10.9999/align-{uuid.uuid4().hex[:8]}"
    paper = Paper(**{"file_path": "/nonexistent.pdf", "title": "t", "doi": doi, "year": 2023, **FULL, **fields})
    session.add(paper)
    await session.commit()
    return paper


async def test_backfill_align_leaves_a_pdf_paper_with_a_doi_read_off_its_page_alone(session):
    paper = await full_paper(session, field_sources={"identifiers": "pdf"})
    client, _ = fake_crossref(crossref_work())
    summary = await backfill_biblio.run(session, client, None, delay=0, only=[paper.id], align=True)
    await session.refresh(paper)
    assert summary["updated"] == 0 and (paper.year, paper.venue, paper.pages) == (2023, None, "289")


@pytest.mark.parametrize("trust", [{"openalex_id": "W9990078"}, {"manual_fields": ["doi"]}, {"file_path": None}])
async def test_a_pdf_stamped_doi_is_trusted_once_openalex_the_owner_or_no_pdf_vouches_for_it(session, trust):
    paper = await full_paper(session, field_sources={"identifiers": "pdf"}, **trust)
    client, _ = fake_crossref(crossref_work())
    await backfill_biblio.run(session, client, None, delay=0, only=[paper.id], align=True)
    await session.refresh(paper)
    assert paper.year == 2024


async def test_a_re_ingest_without_a_match_never_aligns_on_the_leftover_pdf_doi(session):
    paper = await add_paper(session, doi=DOI, year=2023, venue="V", field_sources={"identifiers": "pdf"})
    client, _ = fake_crossref(crossref_work())
    await enrichment.enrich_paper(session, None, paper.id, hints(), crossref_http=client)
    await session.refresh(paper)
    assert (paper.year, paper.venue) == (2023, "V")


def test_a_two_entry_container_title_leaves_the_venue_alone():
    work = crossref_work(type="proceedings-article", **{"container-title": ["Lecture Notes in Computer Science", "X"]})
    fixes = enrichment.align_with_crossref(paper_like(year=2023, venue="LNCS"), work)
    assert "venue" not in fixes and fixes["year"] == 2024


def test_a_chapter_keeps_its_year_and_venue_but_gets_its_page_range():
    work = crossref_work(type="book-chapter", **{"container-title": ["The Book"]})
    assert enrichment.align_with_crossref(paper_like(year=2023, venue="Series", pages="289"), work) == {
        "pages": "289-297"
    }


@pytest.mark.parametrize(("page", "pages"), [("289 – 297", "289-297"), ("289-297a", None), ("e289-e297", None)])
def test_only_a_plain_numeric_range_upgrades_the_page(page, pages):
    fixes = enrichment.align_with_crossref(paper_like(pages="289"), crossref_work(page=page))
    assert fixes.get("pages") == pages


async def test_a_second_align_run_changes_nothing(session):
    paper = await full_paper(session)
    client, _ = fake_crossref(crossref_work())
    first = await backfill_biblio.run(session, client, None, delay=0, only=[paper.id], align=True)
    second = await backfill_biblio.run(session, client, None, delay=0, only=[paper.id], align=True)
    assert (first["updated"], second["updated"]) == (1, 0)


async def test_a_manual_stamp_is_kept_while_the_field_is_corrected(session):
    paper = await full_paper(session, manual_fields=["title"], field_sources={"bibliographic": "manual"})
    client, _ = fake_crossref(crossref_work())
    await backfill_biblio.run(session, client, None, delay=0, only=[paper.id], align=True)
    await session.refresh(paper)
    assert paper.year == 2024 and paper.field_sources["bibliographic"] == "manual"
    assert paper.field_sources["citation"] == "crossref"


async def test_a_plain_backfill_fills_but_never_aligns(session):
    paper = await full_paper(session, pmid=None)
    client, _ = fake_crossref(crossref_work())
    summary = await backfill_biblio.run(session, client, None, delay=0, only=[paper.id])
    await session.refresh(paper)
    assert summary["checked"] == 1 and (paper.year, paper.pages) == (2023, "289")


async def test_the_report_lists_every_change_and_each_one_is_logged(session, tmp_path, caplog):
    import csv  # noqa: PLC0415

    paper = await full_paper(session, volume=None)
    client, _ = fake_crossref(crossref_work(volume="10"))
    report = tmp_path / "changes.csv"
    with caplog.at_level("INFO", logger="app.core.enrichment"):
        await backfill_biblio.run(session, client, None, delay=0, only=[paper.id], align=True, report=report)
    rows = list(csv.DictReader(report.open()))
    assert {(r["field"], r["old"], r["new"]) for r in rows} == {
        ("volume", "", "10"),
        ("year", "2023", "2024"),
        ("venue", "", "Journal of Secondary Gifted Education"),
        ("pages", "289", "289-297"),
    }
    assert {r["paper_id"] for r in rows} == {str(paper.id)} and rows[0]["doi"] == paper.doi
    assert sum("Crossref aligns" in m for m in caplog.messages) == 3


def test_the_cli_passes_align_and_report(monkeypatch):
    seen = {}

    async def main(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(backfill_biblio, "main", main)
    backfill_biblio.cli(["--align", "--dry-run", "--report", "out.csv"])
    assert seen == {"dry_run": True, "align": True, "report": "out.csv"}
