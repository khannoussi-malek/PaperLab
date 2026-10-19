import uuid

import pytest

from app.core import tags, workspaces
from app.models import Chunk, Paper

pytestmark = pytest.mark.anyio


async def _chunked_paper(session, file_path: str | None) -> Paper:
    paper = Paper(title="Abstract only", abstract="An abstract.", file_path=file_path, status="ready")
    session.add(paper)
    await session.flush()
    session.add(
        Chunk(paper_id=paper.id, ordinal=0, page=0, bbox=[], text="An abstract.", embed_model="t", strategy_ver=1)
    )
    await session.commit()
    await session.refresh(paper)
    return paper


async def test_a_paper_without_a_pdf_with_a_chunked_abstract_reports_abstract(session):
    bare = await _chunked_paper(session, None)
    assert (bare.has_pdf, bare.evidence_access) == (False, "abstract")
    filed = await _chunked_paper(session, "/x.pdf")
    assert (filed.has_pdf, filed.evidence_access) == (True, "full_text")


async def test_paper_out_carries_has_pdf_and_details_source(client, session):
    paper = Paper(title="No file", file_path=None, details_source="crossref")
    session.add(paper)
    await session.commit()
    await session.refresh(paper)  # loads the column properties the response reads
    body = (await client.get(f"/api/papers/{paper.id}")).json()
    assert (body["has_pdf"], body["details_source"], body["evidence_access"]) == (False, "crossref", "metadata")


async def test_details_source_only_stores_known_sources(session):
    from sqlalchemy.exc import IntegrityError

    session.add(Paper(title="Bad", file_path=None, details_source="the-moon"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_the_tags_full_text_filter_skips_papers_without_a_pdf(session):
    ws = (await workspaces.create(session, f"nopdf-{uuid.uuid4().hex[:6]}")).id
    bare = await _chunked_paper(session, None)
    filed = await _chunked_paper(session, "/x.pdf")
    for p in (bare, filed):
        await workspaces.add_paper(session, ws, p.id)
    await tags.tag_papers(session, ws, "t", paper_ids=[bare.id, filed.id])
    (row,) = await tags.summaries(session, ws)
    assert (row.full_text, row.abstract) == (1, 1)
