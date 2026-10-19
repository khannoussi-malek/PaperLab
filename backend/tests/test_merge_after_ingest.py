"""PR 3 (R17): a plain upload (M) whose ingest learns a DOI or OpenAlex id a paper saved without a PDF (K) already
holds merges into K at the end of ingest. A holder with a PDF is today's duplicate: both papers stay, no audit row."""

import logging
import uuid

import pytest
from conftest import recorded
from sqlalchemy import func, select

from app.core import merges, paper_sources, papers
from app.core.enrichment import Collision
from app.models import Chunk, Paper, PaperMerge
from app.workers import ingest

pytestmark = pytest.mark.anyio

DOI = "10.18653/v1/n19-1423"  # the DOI doi_pdf prints
PDF_TITLE = "A Paper With a Printed DOI"  # doi_pdf's title; its embedded authors are Jacob Devlin and Ming-Wei Chang


@pytest.fixture
def worker_ctx(ctx, fake_openalex):
    """OpenAlex off (worker_session hides the paper sources), so enrichment falls back to the DOI the PDF prints;
    fake_openalex hides the dev database's papers with that DOI and answers any Crossref request with a 404."""
    return {**ctx, "transport": fake_openalex.transport}


async def saved_without_pdf(session, **fields) -> Paper:
    prefill = {"title": PDF_TITLE, "authors": ["Jacob Devlin"], "doi": DOI, **fields}
    return await papers.create_metadata_paper(session, prefill, "crossref")


async def upload(session, path) -> uuid.UUID:
    paper = Paper(file_path=str(path), title="placeholder")
    session.add(paper)
    await session.commit()
    return paper.id


async def paper_row(session, paper_id) -> Paper | None:
    return await session.scalar(select(Paper).where(Paper.id == paper_id).execution_options(populate_existing=True))


async def audit(session, *paper_ids) -> list[tuple[str, str | None]]:
    query = select(PaperMerge.status, PaperMerge.reason).where(PaperMerge.merged_id.in_(paper_ids))
    return [tuple(row) for row in await session.execute(query)]


async def test_an_upload_whose_doi_a_pdfless_paper_holds_is_merged_after_ingest(worker_session, doi_pdf, worker_ctx):
    k = await saved_without_pdf(worker_session)
    m_id = await upload(worker_session, doi_pdf)

    await ingest.ingest_paper(worker_ctx, str(m_id))

    assert await paper_row(worker_session, m_id) is None
    kept = await paper_row(worker_session, k.id)
    assert (kept.file_path, kept.status, kept.doi) == (str(doi_pdf), "ready", DOI)
    chunks = select(func.count()).select_from(Chunk).where(Chunk.paper_id == k.id, Chunk.page >= 1)
    assert await worker_session.scalar(chunks) > 0  # M's chunks, now K's
    assert await audit(worker_session, m_id) == [("merged", None)]


async def test_a_lookalike_upload_is_reported_and_both_stay(worker_session, doi_pdf, worker_ctx):
    k = await saved_without_pdf(worker_session, title="Another Paper Entirely")
    m_id = await upload(worker_session, doi_pdf)

    await ingest.ingest_paper(worker_ctx, str(m_id))

    m, kept = await paper_row(worker_session, m_id), await paper_row(worker_session, k.id)
    assert (m.status, m.doi, m.file_path) == ("ready", None, str(doi_pdf))
    assert (kept.file_path, kept.doi) == (None, DOI)
    assert await audit(worker_session, m_id) == [("reported", "not_the_same_work")]


async def test_an_upload_whose_doi_a_pdf_paper_holds_is_unchanged(worker_session, doi_pdf, worker_ctx):
    first = Paper(file_path="/first-copy.pdf", title=PDF_TITLE, doi=DOI, status="ready")
    worker_session.add(first)
    await worker_session.commit()
    m_id = await upload(worker_session, doi_pdf)

    await ingest.ingest_paper(worker_ctx, str(m_id))

    m, holder = await paper_row(worker_session, m_id), await paper_row(worker_session, first.id)
    assert (m.status, m.doi) == ("ready", None)
    assert (holder.file_path, holder.doi) == ("/first-copy.pdf", DOI)
    assert await audit(worker_session, m_id, first.id) == []


async def test_a_failing_merge_leaves_the_ingested_paper_ready(
    worker_session, doi_pdf, worker_ctx, monkeypatch, caplog
):
    async def broken(*args, **kwargs):
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(merges, "merge", broken)
    k = await saved_without_pdf(worker_session)
    m_id = await upload(worker_session, doi_pdf)

    with caplog.at_level(logging.ERROR):
        await ingest.ingest_paper(worker_ctx, str(m_id))

    m, kept = await paper_row(worker_session, m_id), await paper_row(worker_session, k.id)
    assert (m.status, m.status_error, m.file_path) == ("ready", None, str(doi_pdf))
    assert (kept.file_path, kept.doi) == (None, DOI)
    assert "the disk is full" in caplog.text  # logged, not raised


async def test_two_pdfless_holders_are_reported_and_neither_merges(worker_session, doi_pdf, worker_ctx, fake_openalex):
    """M's DOI is held by K1 and its OpenAlex id by K2: two different papers, so which is M is unclear."""
    await paper_sources.update(worker_session, {"contact_email": fake_openalex.MAILTO, "enabled": {"openalex": True}})
    fake_openalex.route(f"/works/doi:{DOI}", recorded("work_bert"))
    fake_openalex.route("/authors", {"results": []})
    k1 = await saved_without_pdf(worker_session)
    k2 = await saved_without_pdf(worker_session, doi=None, openalex_id="W2963341956")
    m_id = await upload(worker_session, doi_pdf)

    await ingest.ingest_paper(worker_ctx, str(m_id))

    for paper_id in (m_id, k1.id, k2.id):
        assert await paper_row(worker_session, paper_id) is not None
    assert (await paper_row(worker_session, k1.id)).file_path is None
    assert (await paper_row(worker_session, k2.id)).file_path is None
    assert await audit(worker_session, m_id) == [("reported", "holders_disagree")]


async def test_after_ingest_with_no_pdfless_holder_does_nothing(session):
    holder = Paper(file_path="/first-copy.pdf", title=PDF_TITLE, doi=DOI)
    m = Paper(file_path="/second-copy.pdf", title=PDF_TITLE)
    session.add_all([holder, m])
    await session.commit()

    assert await merges.after_ingest(session, m.id, []) is None
    assert await merges.after_ingest(session, m.id, [Collision("doi", DOI, holder.id)]) is None
    assert await audit(session, m.id) == []
