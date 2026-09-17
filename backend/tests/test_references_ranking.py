"""Asking for a fetch, embedding titles and notes, and ranking references for the library (M7.5)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import unit_vector
from sqlalchemy import delete, func, select, update

from app.core import references
from app.core.errors import NotFound
from app.models import ExternalRef, Note, NoteEmbedding, Paper, paper_references

pytestmark = pytest.mark.anyio

READER_DOI = "10.5555/m75-reader"
REFS = f"/graph/v1/paper/DOI:{READER_DOI}/references"
CITING = f"/graph/v1/paper/DOI:{READER_DOI}/citations"
PDF = b"%PDF-1.7\n%a reference\n"


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


# --- request_fetch -----------------------------------------------------------------------------------------------


async def test_a_second_request_while_fetching_queues_nothing_until_it_goes_stale(library):
    reader = await add_paper(library, doi=READER_DOI)

    assert await references.request_fetch(library, reader.id) is True
    assert await references.request_fetch(library, reader.id) is False
    await library.execute(
        update(Paper)
        .where(Paper.id == reader.id)
        .values(references_requested_at=func.now() - references.FETCH_STALE * 2)
    )
    assert await references.request_fetch(library, reader.id) is True
    with pytest.raises(NotFound):
        await references.request_fetch(library, uuid.uuid4())


# --- embeddings --------------------------------------------------------------------------------------------------


async def test_only_missing_or_stale_vectors_are_embedded(library, embedder):
    reader = await add_paper(library, doi=READER_DOI)
    library.add_all([ExternalRef(title="Needs a vector"), Note(body="a note about attention", provenance="human")])
    await library.flush()

    await references.embed_new(library, embedder)
    await references.embed_new(library, embedder)  # nothing new

    assert [texts for texts, _ in embedder.calls] == [
        ["search_document: Needs a vector"],
        ["search_document: a note about attention"],
    ]
    await library.execute(update(Note).values(body="edited", updated_at=func.now() + timedelta(seconds=1)))
    await references.embed_new(library, embedder)
    assert embedder.calls[-1][0] == ["search_document: edited"]
    assert reader.id  # the paper itself is untouched


# --- ranking -----------------------------------------------------------------------------------------------------


async def link(session, paper, *refs, direction="cites"):
    await session.execute(
        paper_references.insert(),
        [{"paper_id": paper.id, "ref_id": r.id, "direction": direction, "position": i} for i, r in enumerate(refs)],
    )


async def test_a_reference_two_library_papers_cite_outranks_a_famous_uncited_one(library):
    reader = await add_paper(library, doi=READER_DOI)
    second = await add_paper(library, doi="10.5555/m75-second")
    famous = ExternalRef(title="Famous", cited_by_count=100_000)
    shared = ExternalRef(title="Shared", cited_by_count=5)
    library.add_all([famous, shared])
    await library.flush()
    await link(library, reader, famous, shared)
    await link(library, second, shared)

    listing = await references.listing(library, reader.id, "cites")

    assert [(r.title, r.cocitation) for r in listing.rows] == [("Shared", 2), ("Famous", 1)]


async def test_ties_break_on_closeness_to_notes_then_a_free_pdf_then_citations(library):
    reader = await add_paper(library, doi=READER_DOI)
    note = Note(body="n", provenance="human")
    library.add(note)
    await library.flush()
    near, far = unit_vector("near"), unit_vector("far")
    library.add(NoteEmbedding(note_id=note.id, embedding=near, embed_model="test", noted_at=datetime.now(timezone.utc)))
    close = ExternalRef(title="Close to a note", title_embedding=near, title_embed_model="test", cited_by_count=1)
    with_pdf = ExternalRef(
        title="Has a PDF", title_embedding=far, title_embed_model="test", pdf_urls=["https://x/p.pdf"]
    )
    cited = ExternalRef(title="Cited more", title_embedding=far, title_embed_model="test", cited_by_count=900)
    library.add_all([close, with_pdf, cited])
    await library.flush()
    await link(library, reader, cited, with_pdf, close)

    listing = await references.listing(library, reader.id, "cites")

    assert [r.title for r in listing.rows] == ["Close to a note", "Has a PDF", "Cited more"]


async def test_the_summary_counts_references_cited_three_times_and_those_with_pdfs(library):
    papers_ = [await add_paper(library, doi=f"10.5555/m75-{i}") for i in range(3)]
    common = ExternalRef(title="Common", pdf_urls=["https://x/p.pdf"])
    rare = ExternalRef(title="Rare")
    library.add_all([common, rare])
    await library.flush()
    for paper in papers_:
        await link(library, paper, common)
    await link(library, papers_[0], rare)

    listing = await references.listing(library, papers_[0].id, "cites")

    assert (listing.summary.cited_by_3plus, listing.summary.with_pdf) == (1, 1)
    assert listing.state == "none"


async def test_a_reference_uploaded_after_the_fetch_still_shows_in_library(library):
    reader = await add_paper(library, doi=READER_DOI)
    ref = ExternalRef(title="Later uploaded", doi="10.5555/M75-Later")
    library.add(ref)
    await library.flush()
    await link(library, reader, ref)
    uploaded = await add_paper(library, doi="10.5555/m75-later")

    [row] = (await references.listing(library, reader.id, "cites")).rows

    assert row.paper_id == uploaded.id
