"""Fetching a paper's references and citing works, and folding rows that turn out to be one paper (M7.5)."""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete, func, select
from test_references_providers import PagedS2, recorded_references

from app.core import references
from app.core.errors import Conflict
from app.models import ExternalRef, Note, NoteEmbedding, Paper, paper_references
from app.providers import semantic_scholar

pytestmark = pytest.mark.anyio

READER_DOI = "10.5555/m75-reader"
REFS = f"/graph/v1/paper/DOI:{READER_DOI}/references"
CITING = f"/graph/v1/paper/DOI:{READER_DOI}/citations"
PDF = b"%PDF-1.7\n%a reference\n"
# How Semantic Scholar lists a reference it knows nothing about (the recorded BERT page 2 has four).
NO_IDS = {"paperId": None, "title": "Corpus of linguistic acceptability", "year": 2018, "venue": "", "authors": [],
          "externalIds": None, "openAccessPdf": None, "citationCount": None}  # fmt: skip


@pytest.fixture
async def library(session):
    """The dev database (D15) may hold the owner's references, note vectors and notes; hide them in this test's
    rolled-back transaction so counts and similarities are this test's own."""
    for model in (paper_references, NoteEmbedding, ExternalRef, Note):
        await session.execute(delete(model))
    return session


async def add_paper(session, **fields) -> Paper:
    paper = Paper(file_path="/nonexistent.pdf", **{"title": "A library paper", **fields})
    session.add(paper)
    await session.flush()
    return paper


def s2(title: str, doi: str | None = None, year: int = 2020, cites: int = 10, pdf: str = "", **ids) -> dict:
    external = {"DOI": doi} if doi else {}
    return {
        "paperId": ids.get("paper_id") or uuid.uuid5(uuid.NAMESPACE_URL, title).hex + "00000000",
        "title": title,
        "year": year,
        "venue": "Venue",
        "authors": [{"name": "Ada Lovelace"}],
        "externalIds": external,
        "citationCount": cites,
        "openAccessPdf": {"url": pdf},
    }


def page(field: str, *records: dict) -> dict:
    return {"offset": 0, "data": [{field: record} for record in records]}


async def stored(session, paper_id, direction="cites") -> list[str]:
    rows = await session.execute(
        select(ExternalRef.title)
        .join(paper_references, paper_references.c.ref_id == ExternalRef.id)
        .where(paper_references.c.paper_id == paper_id, paper_references.c.direction == direction)
        .order_by(paper_references.c.position)
    )
    return list(rows.scalars())


# --- fetch -------------------------------------------------------------------------------------------------------


async def test_both_directions_are_stored_and_citing_works_come_newest_first(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI)
    discovery_fakes.s2.reply(
        REFS, 200, json=page("citedPaper", s2("Older idea", "10.5555/a"), s2("Method", "10.5555/b"))
    )
    discovery_fakes.s2.reply(
        CITING, 200, json=page("citingPaper", s2("Follow-up 2019", year=2019), s2("Critique 2024", year=2024))
    )

    notices = await references.fetch(library, discovery_fakes.providers, reader)

    assert notices == []
    assert await stored(library, reader.id) == ["Older idea", "Method"]
    assert await stored(library, reader.id, "cited_by") == ["Critique 2024", "Follow-up 2019"]


async def test_openalex_is_merged_when_on_and_one_paper_is_one_row(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI, openalex_id="W9000000750")
    shared = {"id": "https://openalex.org/W9000000751", "doi": "https://doi.org/10.5555/shared", "title": "Shared"}
    discovery_fakes.openalex.route("/works/W9000000750", {"referenced_works": ["https://openalex.org/W9000000751"]})
    discovery_fakes.openalex.route("/works?openalex_id:W9000000751", {"results": [shared]})
    discovery_fakes.openalex.route("/works?cites:W9000000750", {"results": []})
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", s2("Shared", "10.5555/SHARED"), s2("Only in S2")))
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    await references.fetch(library, discovery_fakes.providers, reader)

    assert sorted(await stored(library, reader.id)) == ["Only in S2", "Shared"]
    [row] = await library.scalars(select(ExternalRef).where(ExternalRef.title == "Shared"))
    assert (row.openalex_id, row.s2_id is not None, row.doi) == ("W9000000751", True, "10.5555/shared")


async def test_openalex_is_not_asked_when_it_is_off(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI, openalex_id="W9000000750")
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", s2("A reference")))
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    await references.fetch(library, replace(discovery_fakes.providers, openalex=None), reader)

    assert discovery_fakes.openalex.requests == []
    assert await stored(library, reader.id) == ["A reference"]


async def test_one_failing_source_is_a_notice_beside_the_other_sources_rows(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI, openalex_id="W9000000750")
    discovery_fakes.openalex.route("/works/W9000000750", httpx.Response(503, text="unavailable"))
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", s2("From Semantic Scholar")))
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    notices = await references.fetch(library, discovery_fakes.providers, reader)

    assert notices == ["OpenAlex is busy or unreachable."]
    assert await stored(library, reader.id) == ["From Semantic Scholar"]


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("off", references.REFERENCES_OFF),
        ("unknown", references.REFERENCES_UNKNOWN),
        ("busy", "Semantic Scholar is busy or unreachable."),
    ],
)
async def test_no_answer_at_all_is_a_conflict_that_says_why(library, discovery_fakes, setup, message):
    reader = await add_paper(library, doi=READER_DOI)
    providers = replace(discovery_fakes.providers, openalex=None)
    if setup == "off":
        providers = replace(providers, s2=None)
    elif setup == "unknown":
        discovery_fakes.s2.reply(REFS, 404, json={"error": "Paper not found"})
    else:
        discovery_fakes.s2.refuse(REFS)

    with pytest.raises(Conflict, match=f"^{message}$"):
        await references.fetch(library, providers, reader)


async def test_a_second_fetch_replaces_the_links_without_duplicating_references(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI)
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))
    discovery_fakes.s2.reply(
        REFS, 200, json=page("citedPaper", s2("Kept", "10.5555/kept"), s2("Dropped", "10.5555/gone"))
    )
    await references.fetch(library, discovery_fakes.providers, reader)
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", s2("Kept, retitled", "10.5555/kept")))

    await references.fetch(library, discovery_fakes.providers, reader)

    assert await stored(library, reader.id) == ["Kept, retitled"]
    assert await library.scalar(select(func.count()).select_from(ExternalRef)) == 2  # the dropped row stays for others


async def test_two_stored_rows_found_to_be_one_paper_fold_into_the_oldest(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI)
    other = await add_paper(library, doi="10.5555/m75-other")
    by_s2 = ExternalRef(s2_id="a" * 40, title="Known by id", fetched_at=datetime.now(timezone.utc) - timedelta(days=1))
    by_doi = ExternalRef(doi="10.5555/fold", title="Known by DOI")
    library.add_all([by_s2, by_doi])
    await library.flush()
    await library.execute(
        paper_references.insert().values(paper_id=other.id, ref_id=by_doi.id, direction="cites", position=0)
    )
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", s2("One paper", "10.5555/fold", paper_id="a" * 40)))
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    await references.fetch(library, discovery_fakes.providers, reader)

    [row] = await library.scalars(select(ExternalRef))
    assert (row.id, row.s2_id, row.doi) == (by_s2.id, "a" * 40, "10.5555/fold")
    assert await stored(library, other.id) == ["One paper"]  # the other paper's link moved to the kept row


async def test_duplicate_fold_preserves_pdf_urls_from_all_rows(library, discovery_fakes):
    """When two stored rows fold, the surviving row keeps PDF URLs from both the keeper and duplicates."""
    reader = await add_paper(library, doi=READER_DOI)
    # One row known by s2_id, holds a PDF URL
    by_s2 = ExternalRef(
        s2_id="b" * 40,
        doi="10.5555/m75-pdf-keep",
        title="Known by id with URL",
        pdf_urls=["https://example.org/kept.pdf"],
        fetched_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    # Another row known by doi, no URLs
    by_doi = ExternalRef(doi="10.5555/m75-pdf-keep", title="Known by DOI no URLs", pdf_urls=[])
    library.add_all([by_s2, by_doi])
    await library.flush()
    # Fetch returns a candidate with both IDs but no PDF URL
    discovery_fakes.s2.reply(
        REFS, 200, json=page("citedPaper", s2("Merged paper", "10.5555/m75-pdf-keep", paper_id="b" * 40, pdf=""))
    )
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    await references.fetch(library, discovery_fakes.providers, reader)

    # After folding, exactly one row remains, and it still has the PDF URL
    [row] = await library.scalars(select(ExternalRef))
    assert row.s2_id == "b" * 40
    assert row.doi == "10.5555/m75-pdf-keep"
    assert "https://example.org/kept.pdf" in row.pdf_urls


async def test_imported_row_wins_fold_and_keeps_imported_as(library, discovery_fakes):
    """When folding duplicates, an imported row (one with imported_as set) wins over non-imported rows."""
    reader = await add_paper(library, doi=READER_DOI)
    imported_paper = await add_paper(library, doi="10.5555/m75-imported-winner")
    # Older row without import
    older_unimported = ExternalRef(
        s2_id="c" * 40,
        doi="10.5555/m75-same-paper",
        title="Older, not imported",
        fetched_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    # Newer row with import (should win despite being newer due to import status)
    newer_imported = ExternalRef(
        s2_id=None,
        openalex_id="W9999999",
        doi="10.5555/m75-same-paper",
        title="Newer, imported",
        imported_as=imported_paper.id,
        fetched_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    library.add_all([older_unimported, newer_imported])
    await library.flush()
    # Fetch returns a candidate with the s2_id, DOI, and openalex_id
    discovery_fakes.s2.reply(
        REFS,
        200,
        json=page(
            "citedPaper",
            s2("Merged paper", "10.5555/m75-same-paper", paper_id="c" * 40, openalex_id="W9999999"),
        ),
    )
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    await references.fetch(library, discovery_fakes.providers, reader)

    # After folding, exactly one row remains: the imported one
    [row] = await library.scalars(select(ExternalRef))
    assert row.id == newer_imported.id
    assert row.imported_as == imported_paper.id
    assert row.s2_id == "c" * 40  # merged from older row
    assert row.openalex_id == "W9999999"  # from newer row


async def test_recorded_references_with_no_id_are_skipped_and_every_other_one_is_stored(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI)
    pages = [recorded_references("s2_references_bert_page1"), recorded_references("s2_references_bert_page2")]
    fake = PagedS2()
    fake.page(REFS, 0, pages[0])
    fake.page(REFS, 40, pages[1])
    fake.page(CITING, 0, page("citingPaper"))
    records = [item["citedPaper"] for body in pages for item in body["data"]]
    with_an_id = [record["title"] for record in records if record["paperId"]]

    async with semantic_scholar.new_client(None, transport=fake.transport) as client:
        providers = replace(discovery_fakes.providers, s2=client, openalex=None)
        notices = await references.fetch(library, providers, reader)

    assert (notices, len(records), len(with_an_id)) == ([], 63, 59)
    assert await stored(library, reader.id) == with_an_id


async def test_a_record_with_no_id_leaves_other_papers_references_alone(library, discovery_fakes):
    other = await add_paper(library, doi="10.5555/m75-other")
    theirs = [ExternalRef(s2_id=c * 40, title=f"Their reference {c}") for c in "de"]
    library.add_all(theirs)
    await library.flush()
    await library.execute(
        paper_references.insert(),
        [{"paper_id": other.id, "ref_id": r.id, "direction": "cites", "position": i} for i, r in enumerate(theirs)],
    )
    reader = await add_paper(library, doi=READER_DOI)
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", NO_IDS, s2("Known", paper_id="c" * 40)))
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper", NO_IDS))

    await references.fetch(library, discovery_fakes.providers, reader)

    assert await stored(library, other.id) == ["Their reference d", "Their reference e"]
    assert (await stored(library, reader.id), await stored(library, reader.id, "cited_by")) == (["Known"], [])
    assert await library.scalar(select(func.count()).select_from(ExternalRef)) == 3


async def test_a_row_stored_earlier_in_the_same_fetch_can_fold_into_an_older_one(library, discovery_fakes):
    reader = await add_paper(library, doi=READER_DOI)
    older = ExternalRef(s2_id="y" * 40, title="Beta", fetched_at=datetime.now(timezone.utc) - timedelta(days=1))
    library.add(older)
    await library.flush()
    # The two Alpha records (same title and author) merge into one candidate, stored first as a new row with the DOI.
    # Beta shares that DOI, so storing Beta folds the new Alpha row into the older Beta row, after Alpha's link.
    beta = s2("Beta", "10.5555/m75-shared", paper_id="y" * 40) | {"authors": [{"name": "Grace Hopper"}]}
    alpha, alpha_with_doi = s2("Alpha", paper_id="x" * 40), s2("Alpha", "10.5555/m75-shared", paper_id="z" * 40)
    discovery_fakes.s2.reply(REFS, 200, json=page("citedPaper", alpha, beta, alpha_with_doi))
    discovery_fakes.s2.reply(CITING, 200, json=page("citingPaper"))

    await references.fetch(library, discovery_fakes.providers, reader)

    [row] = await library.scalars(select(ExternalRef))
    assert (row.id, row.doi) == (older.id, "10.5555/m75-shared")
    assert await stored(library, reader.id) == ["Beta"]
