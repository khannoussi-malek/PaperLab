"""R10–R12(1): a paper saved without a PDF upgrades in place when its PDF arrives, by upload or a found free copy."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from starlette.datastructures import UploadFile
from test_discovery_add import arxiv_entry, atom
from test_retrieved_hits import failed_hit, workspace

from app.api import papers as papers_api
from app.api.deps import get_discovery
from app.core import discovery, notes, papers, retrieved_hits, tags, workspaces
from app.core.errors import Conflict
from app.core.prisma_export import prisma_export
from app.models import Paper
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit
from app.workers import ingest

pytestmark = pytest.mark.anyio

ABSTRACT = "Sleep helps memory consolidation in adults."
PREFILL = {"title": "Sleep and memory", "abstract": ABSTRACT, "manual_fields": ["title"]}
PDF = b"%PDF-1.7\n%a found paper\n"
HOST = "https://pdf.example"


async def awaiting(session, ws, held: Paper) -> WorkspaceSearchHit:
    """A relevant hit linked to `held` while it has no PDF, as import_hits and link leave it (R8)."""
    hit = await failed_hit(session, ws, title=held.title, status="awaiting_pdf")
    hit.paper_id = held.id
    await session.commit()
    return hit


async def test_an_upgrade_keeps_id_tags_notes_workspaces_and_decisions(worker_session, ctx, sample_pdf, pdf_dir):
    session = worker_session
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")
    await ingest.index_abstract(ctx, str(held.id))  # as Save without PDF leaves it: ready, its abstract indexed
    ws = await workspace(session)
    await workspaces.add_paper(session, ws.id, held.id)
    await tags.tag_papers(session, ws.id, "sleep", paper_ids=[held.id])
    note = await notes.create_llm_note(session, held.id, "Worth citing.", "Sleep helps memory")
    hit = await awaiting(session, ws, held)
    session.add(SearchRunEligibility(
        paper_id=held.id, search_run_id=ws.run_id, stage2_status="include", assessed_at=datetime.now(timezone.utc),
    ))  # fmt: skip
    await session.commit()

    upgraded = await papers.attach_pdf(session, held.id, sample_pdf.read_bytes(), how="manual")
    await ingest.ingest_paper(ctx, str(held.id))

    await session.refresh(upgraded)
    assert upgraded.id == held.id
    assert (upgraded.has_pdf, upgraded.file_path, upgraded.status) == (True, str(pdf_dir / f"{held.id}.pdf"), "ready")
    assert (upgraded.title, upgraded.details_source, upgraded.abstract) == ("Sleep and memory", "crossref", ABSTRACT)
    assert [(w, t) for w, _, t in await tags.tags_of_paper(session, held.id)] == [(ws.id, ["sleep"])]
    assert upgraded.workspace_ids == [ws.id]
    assert [n.id for n in await notes.list_notes_for_paper(session, held.id)] == [note.id]
    chunks = await papers.list_chunks(session, held.id)
    assert chunks and papers.ABSTRACT_PAGE not in {c.page for c in chunks}  # the PDF's chunks replace the abstract
    hit = await session.get(WorkspaceSearchHit, hit.id, populate_existing=True)
    assert (hit.acquisition_status, hit.paper_id) == ("manual", held.id)
    decision = await session.get(SearchRunEligibility, (held.id, ws.run_id))
    assert decision.stage2_status == "include"
    prisma = await prisma_export(session, ws.id, run_id=None)
    assert (prisma.not_retrieved, prisma.stage2_assessed, prisma.included) == (0, 1, 1)


async def test_attach_pdf_refuses_a_paper_that_has_one(session, pdf_dir):
    filed = Paper(title="Has a file", file_path="/kept.pdf", status="ready")
    session.add(filed)
    await session.commit()

    with pytest.raises(Conflict, match="already_has_pdf"):
        await papers.attach_pdf(session, filed.id, PDF, how="manual")

    await session.refresh(filed)
    assert (filed.file_path, filed.status, list(pdf_dir.glob("*")) if pdf_dir.exists() else []) == (
        "/kept.pdf", "ready", [],
    )  # fmt: skip


async def test_attach_pdf_moves_awaiting_hits_to_retrieved(session, pdf_dir):
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")
    other = await papers.create_metadata_paper(session, {**PREFILL, "title": "Another paper"}, "crossref")
    first, second = await workspace(session), await workspace(session)
    for ws in (first, second):
        await workspaces.add_paper(session, ws.id, held.id)
    hits = [await awaiting(session, first, held), await awaiting(session, second, held)]
    untouched = await awaiting(session, first, other)
    assert (await prisma_export(session, first.id, run_id=None)).not_retrieved == 2

    await papers.attach_pdf(session, held.id, PDF, how="imported")

    statuses = [(await session.get(WorkspaceSearchHit, h.id, populate_existing=True)).acquisition_status for h in hits]
    assert statuses == ["imported", "imported"]
    await session.refresh(untouched)
    assert untouched.acquisition_status == "awaiting_pdf"
    assert (await prisma_export(session, first.id, run_id=None)).not_retrieved == 1
    with pytest.raises(ValueError, match="how"):
        await retrieved_hits.pdf_arrived(session, other.id, "failed")


async def test_upload_pdf_route_upgrades_and_queues_ingest(client, session, arq, pdf_dir):
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")
    ws = await workspace(session)
    hit = await awaiting(session, ws, held)

    not_pdf = await client.post(f"/api/papers/{held.id}/pdf", files={"file": ("x.pdf", b"<html>", "application/pdf")})
    answer = await client.post(f"/api/papers/{held.id}/pdf", files={"file": ("x.pdf", PDF, "application/pdf")})
    again = await client.post(f"/api/papers/{held.id}/pdf", files={"file": ("x.pdf", PDF, "application/pdf")})

    assert (not_pdf.status_code, not_pdf.json()["detail"]) == (422, "not_a_pdf")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert (body["id"], body["has_pdf"], body["status"], body["details_source"]) == (
        str(held.id), True, "uploaded", "crossref",
    )  # fmt: skip
    assert (pdf_dir / f"{held.id}.pdf").read_bytes() == PDF
    assert arq.jobs == [("ingest_paper", str(held.id))]
    await session.refresh(hit)
    assert hit.acquisition_status == "manual"
    assert (again.status_code, again.json()["detail"]) == (409, "already_has_pdf")


async def test_find_pdf_route_upgrades_or_says_what_it_tried(app, client, session, arq, discovery_fakes, pdf_dir):
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.providers
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    discovery_fakes.pdf_host.reply("/gone.pdf", 404)
    found = await papers.create_metadata_paper(session, {**PREFILL, "oa_url": f"{HOST}/copy.pdf"}, "openalex")
    lost = await papers.create_metadata_paper(
        session, {**PREFILL, "title": "Lost", "oa_url": f"{HOST}/gone.pdf"}, "openalex"
    )
    ws = await workspace(session)
    hit = await awaiting(session, ws, found)

    upgraded = await client.post(f"/api/papers/{found.id}/find-pdf")
    missing = await client.post(f"/api/papers/{lost.id}/find-pdf")
    again = await client.post(f"/api/papers/{found.id}/find-pdf")

    assert upgraded.status_code == 200, upgraded.text
    assert (upgraded.json()["id"], upgraded.json()["has_pdf"]) == (str(found.id), True)
    assert (pdf_dir / f"{found.id}.pdf").read_bytes() == PDF
    await session.refresh(hit)
    assert hit.acquisition_status == "imported"
    assert missing.status_code == 409
    assert missing.json() == {
        "detail": "no_free_pdf", "tried": [{"url": f"{HOST}/gone.pdf", "outcome": "http_404"}], "free_copies": [],
    }  # fmt: skip
    await session.refresh(lost)
    assert lost.has_pdf is False
    assert (again.status_code, again.json()["detail"]) == (409, "already_has_pdf")
    assert arq.jobs == [("ingest_paper", str(found.id))]


ARXIV_TITLE = "Sleep and memory in adults"


async def held_preprint(session) -> Paper:
    preprint = Paper(title=ARXIV_TITLE, doi="10.48550/arxiv.2401.00001", file_path="/held.pdf", status="ready")
    session.add(preprint)
    await session.commit()
    return preprint


@pytest.mark.parametrize("doi", ["10.5555/sleep", None])
async def test_find_pdf_route_names_a_held_arxiv_copy_of_the_same_work(
    app, client, session, discovery_fakes, monkeypatch, doi
):
    """The arXiv title search finds a preprint the library already holds: a duplicate, never a second file, and the
    preprint learns nothing: the DOI is the PDF-less paper's own, so it must keep answering to it alone."""
    preprint = await held_preprint(session)
    prefill = {"title": ARXIV_TITLE, "authors": ["Ada Lovelace"], "year": 2024, "doi": doi, "venue": "J. Sleep"}
    held = await papers.create_metadata_paper(session, prefill, "crossref")
    entry = arxiv_entry(title=ARXIV_TITLE, authors=["Ada Lovelace"], id="2401.00001", year=2024)
    discovery_fakes.arxiv.reply("/api/query", 200, text=atom(entry))
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.turned_on("arxiv")
    monkeypatch.setattr(discovery, "_sleep", _no_wait)

    answer = await client.post(f"/api/papers/{held.id}/find-pdf")

    assert (answer.status_code, answer.json()["detail"], answer.json()["paper_id"]) == (
        409, "already_in_library", str(preprint.id),
    )  # fmt: skip
    assert answer.json()["tried"][-1] == {
        "url": f"https://doi.org/{doi}" if doi else "https://arxiv.org/abs/2401.00001", "outcome": "in_library",
    }  # fmt: skip
    await session.refresh(held)
    await session.refresh(preprint)
    assert (held.has_pdf, discovery_fakes.pdf_host.requests) == (False, [])
    assert (preprint.published_doi, preprint.published_venue, preprint.peer_reviewed) == (None, None, "unknown")
    if doi:
        [marked] = await discovery.mark_in_library(session, [discovery.Candidate(title=ARXIV_TITLE, doi=doi)])
        assert marked.paper_id == held.id


async def test_find_pdf_route_never_attaches_a_second_copy_of_a_held_arxiv_paper(app, client, session, discovery_fakes):
    """An arXiv link of its own names a paper the library holds: the same 409 as the title search, nothing fetched."""
    preprint = await held_preprint(session)
    held = await papers.create_metadata_paper(
        session, {**PREFILL, "doi": "10.5555/sleep", "oa_url": "https://arxiv.org/abs/2401.00001"}, "openalex"
    )
    app.dependency_overrides[get_discovery] = lambda: discovery_fakes.providers

    answer = await client.post(f"/api/papers/{held.id}/find-pdf")

    assert (answer.status_code, answer.json()["detail"], answer.json()["paper_id"]) == (
        409, "already_in_library", str(preprint.id),
    )  # fmt: skip
    await session.refresh(held)
    await session.refresh(preprint)
    assert (held.has_pdf, preprint.published_doi, discovery_fakes.pdf_host.requests) == (False, None, [])


async def test_both_routes_answer_404_for_an_unknown_paper_whatever_the_body(client):
    unknown = uuid.uuid4()
    upload = await client.post(f"/api/papers/{unknown}/pdf", files={"file": ("x.pdf", b"<html>", "text/html")})
    find = await client.post(f"/api/papers/{unknown}/find-pdf")
    assert (upload.status_code, find.status_code) == (404, 404)


async def test_an_upload_over_the_cap_is_refused_before_anything_is_stored(client, session, pdf_dir, monkeypatch):
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")
    monkeypatch.setattr(papers_api, "MAX_UPLOAD_PDF_BYTES", len(PDF) - 1)

    async def never_read(*args):
        raise AssertionError("an over-cap body with a known size is refused unread")

    monkeypatch.setattr(UploadFile, "read", never_read)
    answer = await client.post(f"/api/papers/{held.id}/pdf", files={"file": ("x.pdf", PDF, "application/pdf")})

    assert (answer.status_code, answer.json()["detail"]) == (422, "pdf_too_large")
    await session.refresh(held)
    assert (held.has_pdf, pdf_dir.exists() and any(pdf_dir.iterdir())) == (False, False)


async def _no_wait(_seconds):
    return None


async def test_index_abstract_never_marks_an_upgraded_paper_ready(worker_session, pdf_dir):
    """A PDF that lands while index_abstract embeds: ingest owns the paper from then on, so it stays `uploaded`."""
    session = worker_session
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")

    class AttachesMidway:
        name = model = "test"
        label, is_local = "Test", True
        document_prefix, query_prefix = "search_document: ", "search_query: "

        async def encode(self, texts):
            await papers.attach_pdf(session, held.id, PDF, how="manual")
            return [[0.0] * 768 for _ in texts]

    await ingest.index_abstract({"embedder": AttachesMidway()}, str(held.id))

    await session.refresh(held)
    assert (held.has_pdf, held.status) == (True, "uploaded")


def candidate(**fields) -> discovery.Candidate:
    return discovery.Candidate(**{"title": "Found: A Paper", "authors": ["Ada Lovelace"], "year": 2024, **fields})


async def test_add_still_behaves_the_same_after_find_pdf_extraction(session, discovery_fakes, pdf_dir):
    """add() and find_pdf() walk one waterfall: the same URLs, in order, the same outcomes and the same copy."""
    discovery_fakes.pdf_host.reply("/landing", 200, text="<html>a landing page</html>")
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    urls = [f"{HOST}/landing", f"{HOST}/copy.pdf"]
    tried_by_add: list = []

    paper = await discovery.add(session, discovery_fakes.providers, candidate(pdf_urls=urls), pdf_dir, tried_by_add)
    data, tried, copies = await discovery.find_pdf(session, discovery_fakes.providers, candidate(pdf_urls=urls))

    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == data == PDF
    assert tried == tried_by_add == [
        {"url": f"{HOST}/landing", "outcome": "not_a_pdf"}, {"url": f"{HOST}/copy.pdf", "outcome": "pdf"},
    ]  # fmt: skip
    assert copies == []
    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/landing", "/copy.pdf"] * 2


async def test_candidate_of_a_held_paper_carries_its_identifiers(session):
    held = Paper(
        title="Held", authors=["Ada Lovelace"], year=2021, venue="Tests", doi="10.48550/arXiv.2101.00001",
        openalex_id="W123", pmcid="PMC456", oa_url="https://oa.example/held.pdf", file_path=None,
    )  # fmt: skip

    found = discovery.candidate_of(held)

    assert (found.title, found.authors, found.year, found.venue, found.doi) == (
        "Held", ["Ada Lovelace"], 2021, "Tests", "10.48550/arXiv.2101.00001",
    )  # fmt: skip
    assert found.external_ids == {"openalex": "W123", "pmc": "456", "arxiv": "2101.00001"}
    assert found.pdf_urls == ["https://arxiv.org/pdf/2101.00001", "https://oa.example/held.pdf"]
    assert discovery.candidate_of(Paper(title="Bare", authors=[], file_path=None)).external_ids == {}


async def test_attach_pdf_leaves_no_file_when_the_commit_fails(session, pdf_dir, monkeypatch):
    paper_id = (await papers.create_metadata_paper(session, PREFILL, "crossref")).id

    async def fails():
        raise RuntimeError("the database went away")

    monkeypatch.setattr(session, "commit", fails)
    with pytest.raises(RuntimeError):
        await papers.attach_pdf(session, paper_id, PDF, how="manual")

    assert not (pdf_dir / f"{paper_id}.pdf").exists()
    await session.rollback()
    file_path = await session.scalar(select(Paper.file_path).where(Paper.id == paper_id))
    assert file_path is None


async def test_attach_pdf_checks_how_before_writing_anything(session, pdf_dir):
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")

    with pytest.raises(ValueError, match="how"):
        await papers.attach_pdf(session, held.id, PDF, how="failed")

    assert (held.file_path, pdf_dir.exists() and any(pdf_dir.iterdir())) == (None, False)


async def test_attach_pdf_leaves_no_file_when_the_write_breaks_midway(session, pdf_dir, monkeypatch):
    held = await papers.create_metadata_paper(session, PREFILL, "crossref")

    async def half_written(func, data):
        func(data[:4])
        raise OSError("No space left on device")

    monkeypatch.setattr(papers.asyncio, "to_thread", half_written)
    with pytest.raises(OSError):
        await papers.attach_pdf(session, held.id, PDF, how="manual")

    assert list(pdf_dir.iterdir()) == []
