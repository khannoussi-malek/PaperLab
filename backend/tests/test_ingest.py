import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import numpy as np
import pytest
from conftest import recorded, unit_vector
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import enrichment, papers
from app.models import Author, Chunk, Paper, paper_authors, paper_topics
from app.providers import embedding
from app.workers import ingest
from app.workers.settings import WorkerSettings

pytestmark = pytest.mark.anyio


@pytest.fixture
def worker_session(session, monkeypatch):
    """Point the worker at the rolled-back test session instead of its own SessionLocal."""

    @asynccontextmanager
    async def shared_session():
        yield session

    monkeypatch.setattr(ingest, "SessionLocal", shared_session)
    return session


@pytest.fixture
def ctx(embedder):
    """What WorkerSettings.on_startup leaves in the ARQ context, with the fake model."""
    return {"embedder": embedder}


async def add_paper(session, path, **fields) -> Paper:
    paper = Paper(file_path=str(path), **{"title": "placeholder", **fields})
    session.add(paper)
    await session.commit()
    return paper


async def chunks_of(session, paper_id):
    # populate_existing: embeddings are written by a bulk UPDATE, which leaves loaded objects stale.
    query = select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)
    return list(await session.scalars(query.execution_options(populate_existing=True)))


async def test_ingest_reaches_ready_with_embedded_chunks(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error, paper.page_count) == ("ready", None, 2)
    assert paper.title == "Deep Paper Title"
    chunks = await chunks_of(worker_session, paper.id)
    assert {c.page for c in chunks} == {1, 2}
    assert chunks[-1].section_title == "2 Method"
    assert all(c.bbox and c.embedding is not None for c in chunks)


async def test_chunks_are_embedded_with_the_document_prefix(worker_session, sample_pdf, ctx, embedder):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))

    chunks = await chunks_of(worker_session, paper.id)
    prefixed = [f"search_document: {c.text}" for c in chunks]
    assert embedder.calls == [(prefixed, {"batch_size": 16, "normalize_embeddings": True})]
    for chunk, text in zip(chunks, prefixed):
        assert np.allclose(chunk.embedding, unit_vector(text), atol=1e-6)


async def test_model_loads_once_per_worker_not_per_job(worker_session, sample_pdf, embedder, monkeypatch):
    loads = []
    monkeypatch.setattr(embedding, "load", lambda: loads.append("load") or embedder)
    paper = await add_paper(worker_session, sample_pdf)
    worker_ctx = {}

    await WorkerSettings.on_startup(worker_ctx)
    await ingest.ingest_paper(worker_ctx, str(paper.id))
    await ingest.ingest_paper(worker_ctx, str(paper.id))

    assert loads == ["load"]
    assert len(embedder.calls) == 2


async def test_reingest_is_idempotent(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))
    first = [(c.ordinal, c.page, c.text) for c in await chunks_of(worker_session, paper.id)]
    await ingest.ingest_paper(ctx, str(paper.id))
    second = [(c.ordinal, c.page, c.text) for c in await chunks_of(worker_session, paper.id)]

    assert first == second and first


async def test_reingest_replaces_the_vectors(worker_session, sample_pdf, ctx, embedder):
    paper = await add_paper(worker_session, sample_pdf)
    await ingest.ingest_paper(ctx, str(paper.id))
    first = await chunks_of(worker_session, paper.id)

    # A different model version: every text now embeds to another vector.
    embedder.vectors = {f"search_document: {c.text}": unit_vector(f"v2 {c.text}") for c in first}
    await ingest.ingest_paper(ctx, str(paper.id))
    second = await chunks_of(worker_session, paper.id)

    assert {c.id for c in first}.isdisjoint(c.id for c in second)
    for chunk in second:
        assert np.allclose(chunk.embedding, unit_vector(f"v2 {chunk.text}"), atol=1e-6)


async def test_embedder_failure_ends_failed_with_error(worker_session, sample_pdf):
    class ExplodingEmbedder:
        def encode(self, texts, **kwargs):
            raise RuntimeError("model ran out of memory")

    paper = await add_paper(worker_session, sample_pdf)

    await ingest.ingest_paper({"embedder": ExplodingEmbedder()}, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error) == ("failed", "RuntimeError: model ran out of memory")


async def test_pdf_without_text_ends_failed_with_error(worker_session, blank_pdf, ctx):
    paper = await add_paper(worker_session, blank_pdf)

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "failed"
    assert paper.status_error.startswith("InvalidInput: PDF has no usable text layer")
    assert await chunks_of(worker_session, paper.id) == []


async def test_missing_file_ends_failed(worker_session, tmp_path, ctx):
    paper = await add_paper(worker_session, tmp_path / "gone.pdf")

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "failed" and paper.status_error


async def test_enriched_title_is_not_overwritten(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf, openalex_id="W123", title="Title From OpenAlex")

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "ready" and paper.title == "Title From OpenAlex"


BERT_WORK = "/works/doi:10.18653/v1/n19-1423"  # the DOI doi_pdf prints
E2E_FIXTURES = Path(__file__).parents[2] / "frontend/e2e/fixtures"


@pytest.fixture
def statuses(monkeypatch):
    """Every status the worker writes, in order."""
    written = []
    set_status = papers.set_status

    async def recording(session, paper_id, status, *args, **kwargs):
        written.append(str(status))
        await set_status(session, paper_id, status, *args, **kwargs)

    monkeypatch.setattr(papers, "set_status", recording)
    return written


async def count(session, table, paper_id) -> int:
    return await session.scalar(select(func.count()).select_from(table).where(table.c.paper_id == paper_id))


async def test_a_doi_paper_is_enriched_on_its_way_to_ready(worker_session, doi_pdf, ctx, fake_openalex, statuses):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    fake_openalex.route("/authors", recorded("authors_bert"))
    paper = await add_paper(worker_session, doi_pdf)

    await ingest.ingest_paper({**ctx, "openalex": fake_openalex.client}, str(paper.id))
    await worker_session.refresh(paper)

    assert statuses == ["extracting", "chunking", "embedding", "enriching", "ready"]
    assert (paper.status, paper.openalex_id, paper.year) == ("ready", "W2963341956", 2019)
    assert paper.title.startswith("BERT: Pre-training")  # OpenAlex's title replaces the PDF's
    ids = select(Author.openalex_id).join(paper_authors).where(paper_authors.c.paper_id == paper.id)
    assert set(await worker_session.scalars(ids)) == {"A5057457287", "A5076904467", "A5081862885", "A5053947885"}
    assert await count(worker_session, paper_topics, paper.id) == 11  # 9 from OpenAlex, 2 embedded keywords


async def test_a_reingest_keeps_one_row_per_author_and_topic(worker_session, doi_pdf, ctx, fake_openalex, caplog):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    fake_openalex.route("/works/W2963341956", recorded("work_bert"))  # the re-run looks up the now-stored id
    fake_openalex.route("/authors", recorded("authors_bert"))
    paper = await add_paper(worker_session, doi_pdf)
    # Captured once: a failed re-enrichment rolls back inside _enrich, which expires `paper`, and a bare attribute
    # read after that raises MissingGreenlet instead of a clean assertion failure (see ingest.py's _enrich comment).
    paper_id = paper.id
    enriching = {**ctx, "openalex": fake_openalex.client}

    await ingest.ingest_paper(enriching, str(paper_id))
    await ingest.ingest_paper(enriching, str(paper_id))

    assert await count(worker_session, paper_authors, paper_id) == 4
    assert await count(worker_session, paper_topics, paper_id) == 11
    # Those counts alone would look identical if the second run silently skipped re-enrichment (or _enrich's
    # catch-all quietly ate a failure): confirm the re-run actually looked the stored id up again, and cleanly.
    assert [r.url.path for r in fake_openalex.requests].count("/works/W2963341956") == 1
    assert "enrichment failed" not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        None,  # OpenAlex has no such DOI, and title search finds nothing
        httpx.ConnectError("OpenAlex unreachable"),
        httpx.ReadTimeout("OpenAlex timed out"),
        httpx.Response(429, headers={"retry-after": "1"}, json={"error": "Rate limit exceeded"}),
    ],
    ids=["no match", "network error", "timeout", "rate limited"],
)
async def test_without_openalex_the_paper_still_reaches_ready_with_pdf_metadata(
    worker_session, doi_pdf, ctx, fake_openalex, failure
):
    fake_openalex.route("/works", recorded("search_no_match"))
    # "no match": OpenAlex has no such DOI, a clean 404 rather than leaving the request unrouted.
    fake_openalex.route(BERT_WORK, failure if failure is not None else httpx.Response(404))
    paper = await add_paper(worker_session, doi_pdf)

    await ingest.ingest_paper({**ctx, "openalex": fake_openalex.client}, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.status_error, paper.openalex_id) == ("ready", None, None)
    assert paper.authors == ["Jacob Devlin", "Ming-Wei Chang"]  # from the PDF's embedded author field


async def test_a_second_copy_of_a_matched_paper_still_reaches_ready(
    worker_session, doi_pdf, ctx, fake_openalex, caplog
):
    fake_openalex.route(BERT_WORK, recorded("work_bert"))
    # A malformed /authors reply (no "display_name") makes refresh_authors raise a realistic KeyError -- not an
    # accident of FakeOpenAlex's unrouted-request guard -- and _enrich's catch-all is what still lets the paper
    # reach ready.
    fake_openalex.route("/authors", httpx.Response(200, json={"results": [{}]}))
    await add_paper(worker_session, "/first-copy.pdf", doi="10.18653/v1/n19-1423")
    copy = await add_paper(worker_session, doi_pdf)

    await ingest.ingest_paper({**ctx, "openalex": fake_openalex.client}, str(copy.id))
    await worker_session.refresh(copy)

    # papers.doi is UNIQUE: doi is dropped instead of raising (core/enrichment.py's _taken), the rest of the match
    # (title included) still applies -- symmetric with test_enrichment.py's test_a_duplicate_openalex_match_....
    assert (copy.status, copy.status_error, copy.doi) == ("ready", None, None)
    assert copy.title.startswith("BERT: Pre-training")
    assert "enrichment failed" in caplog.text  # _enrich's except actually ran, not a lucky no-op


async def test_a_corrected_title_survives_a_reingest(worker_session, sample_pdf, ctx):
    paper = await add_paper(worker_session, sample_pdf, title="My Own Title", manual_fields=["title"])

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, paper.title) == ("ready", "My Own Title")


async def test_a_title_correction_made_mid_extraction_survives_ingestion(worker_session, sample_pdf, ctx, monkeypatch):
    """`paper` is loaded once at job start; a PATCH racing `extract` must not be clobbered by the font heuristic."""
    paper = await add_paper(worker_session, sample_pdf)
    loop = asyncio.get_running_loop()
    real_extract = ingest.extract

    async def apply_correction():
        # A separate session, as the API's PATCH handler would use -- not `worker_session`'s in-memory `paper`.
        other = AsyncSession(bind=worker_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint")
        async with other:
            await enrichment.correct_metadata(other, paper.id, {"title": "User's Corrected Title"})

    def racing_extract(path):
        doc = real_extract(path)
        # extract() runs in a worker thread (asyncio.to_thread); hop back onto the event loop to commit the
        # correction while ingest_paper is still awaiting this call, simulating the real race.
        asyncio.run_coroutine_threadsafe(apply_correction(), loop).result()
        return doc

    monkeypatch.setattr(ingest, "extract", racing_extract)

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)

    assert paper.status == "ready"
    assert paper.title == "User's Corrected Title"
    assert "title" in paper.manual_fields


@pytest.mark.parametrize("pdf", sorted(E2E_FIXTURES.glob("*.pdf")), ids=lambda p: p.name)
async def test_the_e2e_fixture_paper_sends_no_openalex_request(worker_session, ctx, fake_openalex, pdf):
    # No DOI, no arXiv ID and no creation date: nothing to look up and no year to confirm a title search.
    # This keeps the Playwright stack off the network even with OPENALEX_MAILTO set. Loops over every fixture PDF
    # in the directory (M10), in case another spec adds a second one later.
    paper = await add_paper(worker_session, pdf)

    await ingest.ingest_paper({**ctx, "openalex": fake_openalex.client}, str(paper.id))
    await worker_session.refresh(paper)

    assert (paper.status, fake_openalex.requests) == ("ready", [])


async def test_the_worker_opens_an_openalex_client_only_with_a_mailto(embedder, monkeypatch):
    monkeypatch.setattr(embedding, "load", lambda: embedder)
    monkeypatch.setattr(settings, "openalex_mailto", "")
    off = {}
    await WorkerSettings.on_startup(off)
    assert off["openalex"] is None
    await WorkerSettings.on_shutdown(off)

    monkeypatch.setattr(settings, "openalex_mailto", "me@example.com")
    on = {}
    await WorkerSettings.on_startup(on)
    assert on["openalex"].params["mailto"] == "me@example.com"
    await WorkerSettings.on_shutdown(on)
    assert on["openalex"].is_closed
