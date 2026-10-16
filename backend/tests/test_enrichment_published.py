"""M65: a preprint copy learns its published version from OpenAlex (ingest). Offline (FakeOpenAlex)."""

import pytest

from app.core import enrichment
from app.core.enrichment import PdfHints, openalex_published
from app.models import Paper

pytestmark = pytest.mark.anyio

STOC_DOI = "10.1145/3717823.3718108"
STOC = {
    "id": "https://openalex.org/W4411320050", "doi": f"https://doi.org/{STOC_DOI}", "title": "On the Limits",
    "type": "conference-paper", "publication_year": 2025, "authorships": [],
    "primary_location": {
        "version": "publishedVersion", "source": {"display_name": "Proceedings of STOC (STOC)"},
    },
}
ARXIV_WORK = {
    "id": "https://openalex.org/W1", "doi": "https://doi.org/10.48550/arxiv.2504.06161", "title": "On the Limits",
    "type": "preprint", "publication_year": 2025, "authorships": [],
    "primary_location": {"version": "submittedVersion", "source": {"display_name": "arXiv (Cornell University)"}},
}
ARXIV_DOI = "10.48550/arxiv.2504.06161"


def hints() -> PdfHints:
    return PdfHints(doi=None, arxiv_id=None, years=frozenset(), text="", authors=[], keywords=[])


def test_openalex_published_reads_a_conference_paper():
    assert openalex_published(STOC) == (STOC_DOI, "Proceedings of STOC (STOC)", "proceedings")


def test_an_arxiv_primary_location_is_not_a_published_version():
    assert openalex_published(ARXIV_WORK) == (None, None, None)
    on_arxiv = {**STOC, "primary_location": {"version": "publishedVersion", "source": {"display_name": "arXiv"}}}
    assert openalex_published(on_arxiv) == (None, None, None)


async def locked_copy(session, **fields) -> Paper:
    fields = {"manual_fields": ["doi"], **fields}
    paper = Paper(title="On the Limits", file_path="/x.pdf", doi=ARXIV_DOI, openalex_id="W4411320050", **fields)
    session.add(paper)
    await session.commit()
    return paper


async def run(session, fake, paper) -> Paper:
    fake.route("/works/W4411320050", STOC)
    fake.route("/authors", {"results": []})
    await enrichment.enrich_paper(session, fake.client, paper.id, hints())
    await session.refresh(paper)
    return paper


async def test_ingest_records_the_published_version_for_an_arxiv_copy(session, fake_openalex):
    paper = await run(session, fake_openalex, await locked_copy(session))
    assert (paper.published_doi, paper.published_venue) == (STOC_DOI, "Proceedings of STOC (STOC)")
    assert (paper.peer_reviewed, paper.source_type) == ("true", "preprint")
    assert paper.doi == ARXIV_DOI and "doi" in paper.manual_fields


async def test_manual_fields_still_win(session, fake_openalex):
    paper = await locked_copy(session, published_venue="Mine", manual_fields=["doi", "published_venue"])
    paper = await run(session, fake_openalex, paper)
    assert paper.published_venue == "Mine" and paper.published_doi == STOC_DOI


async def test_a_hand_set_source_type_blocks_peer_review(session, fake_openalex):
    paper = await locked_copy(session, source_type="preprint", manual_fields=["doi", "source_type"])
    paper = await run(session, fake_openalex, paper)
    assert paper.published_doi == STOC_DOI and paper.peer_reviewed == "unknown"
