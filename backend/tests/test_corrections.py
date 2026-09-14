import uuid

import pytest
from conftest import recorded

from app.core import enrichment
from app.core.enrichment import PdfHints
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Paper

pytestmark = pytest.mark.anyio


async def add_paper(session, **fields) -> Paper:
    paper = Paper(file_path="/nonexistent.pdf", **{"title": "BERT: Pre-training of Deep", **fields})
    session.add(paper)
    await session.commit()
    return paper


async def test_corrections_are_written_and_remembered(session):
    paper = await add_paper(session, venue="arXiv", doi="10.1000/original")

    await enrichment.correct_metadata(session, paper.id, {"title": "BERT", "authors": ["Jacob Devlin"]})
    corrected = await enrichment.correct_metadata(
        session, paper.id, {"title": "BERT!", "venue": None, "year": 2019, "doi": None}
    )

    assert (corrected.title, corrected.authors, corrected.venue) == ("BERT!", ["Jacob Devlin"], None)
    assert (corrected.year, corrected.doi) == (2019, None)  # M9: doi: None clears it, the untested branch
    assert corrected.manual_fields == ["authors", "doi", "title", "venue", "year"]


async def test_a_doi_is_normalized_and_must_be_one(session):
    paper = await add_paper(session)

    corrected = await enrichment.correct_metadata(session, paper.id, {"doi": "https://doi.org/10.5555/PaperLab.1"})
    assert corrected.doi == "10.5555/paperlab.1"
    with pytest.raises(InvalidInput, match="^not a DOI: 'arXiv:1810.04805'$"):
        await enrichment.correct_metadata(session, paper.id, {"doi": "arXiv:1810.04805"})


async def test_a_doi_can_belong_to_one_paper_only(session):
    await add_paper(session, doi="10.5555/taken")
    paper = await add_paper(session)

    with pytest.raises(Conflict, match="^doi_taken$"):
        await enrichment.correct_metadata(session, paper.id, {"doi": "10.5555/TAKEN"})


async def test_correcting_an_unknown_paper_is_not_found(session):
    with pytest.raises(NotFound):
        await enrichment.correct_metadata(session, uuid.uuid4(), {"title": "BERT"})


async def test_a_correction_survives_the_next_enrichment(session, fake_openalex):
    fake_openalex.route("/works/doi:10.18653/v1/n19-1423", recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session)
    await enrichment.correct_metadata(session, paper.id, {"title": "My BERT", "is_retracted": True})

    hints = PdfHints(doi="10.18653/v1/n19-1423", arxiv_id=None, years=frozenset(), text="", authors=[], keywords=[])
    await enrichment.enrich_paper(session, fake_openalex.client, paper.id, hints)
    await session.refresh(paper)

    assert (paper.title, paper.is_retracted, paper.year, paper.openalex_id) == ("My BERT", True, 2019, "W2963341956")


# Owner ruling (Task 7): the abstract is correctable, locked the same way as every other manual field.


async def test_a_corrected_abstract_is_written_and_remembered(session):
    paper = await add_paper(session, abstract="OpenAlex's abstract, actually BERT's citation string")

    corrected = await enrichment.correct_metadata(session, paper.id, {"abstract": "The real BERT abstract."})

    assert corrected.abstract == "The real BERT abstract."
    assert corrected.manual_fields == ["abstract"]


async def test_a_corrected_abstract_survives_the_next_enrichment(session, fake_openalex):
    fake_openalex.route("/works/doi:10.18653/v1/n19-1423", recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})  # author details are covered in test_enrichment_authors.py
    paper = await add_paper(session)
    await enrichment.correct_metadata(session, paper.id, {"abstract": "The corrected abstract."})

    hints = PdfHints(doi="10.18653/v1/n19-1423", arxiv_id=None, years=frozenset(), text="", authors=[], keywords=[])
    await enrichment.enrich_paper(session, fake_openalex.client, paper.id, hints)
    await session.refresh(paper)

    # work_bert.json carries its own abstract_inverted_index; the manual correction must still win.
    assert paper.abstract == "The corrected abstract."
