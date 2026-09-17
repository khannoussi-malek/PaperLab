"""Importing a reference: the free PDF becomes a library paper (M7.5, D84)."""

import uuid

import pytest
from sqlalchemy import delete, select

from app.core import references
from app.core.errors import Conflict, NotFound
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


# --- import ------------------------------------------------------------------------------------------------------


async def test_importing_downloads_the_free_pdf_and_marks_the_reference(library, discovery_fakes, pdf_dir):
    ref = ExternalRef(title="Importable", doi="10.5555/m75-import", pdf_urls=["https://pdf.example/ref.pdf"])
    library.add(ref)
    await library.flush()
    discovery_fakes.pdf_host.reply("/ref.pdf", 200, content=PDF)

    paper = await references.import_reference(library, discovery_fakes.providers, ref.id, pdf_dir)

    await library.refresh(ref)
    assert (ref.imported_as, paper.doi, paper.title) == (paper.id, "10.5555/m75-import", "Importable")
    with pytest.raises(Conflict, match="already in your library"):
        await references.import_reference(library, discovery_fakes.providers, ref.id, pdf_dir)


async def test_a_reference_without_a_free_pdf_or_unknown_cannot_be_imported(library, discovery_fakes, pdf_dir):
    closed = ExternalRef(title="Closed")
    library.add(closed)
    await library.flush()

    with pytest.raises(Conflict, match="No free PDF"):
        await references.import_reference(library, discovery_fakes.providers, closed.id, pdf_dir)
    with pytest.raises(NotFound):
        await references.import_reference(library, discovery_fakes.providers, uuid.uuid4(), pdf_dir)
