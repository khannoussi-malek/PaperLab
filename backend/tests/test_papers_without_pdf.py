import base64
import io
import uuid
import zipfile

import pytest
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from sqlalchemy import func, select

from app.core import chunking, evidence_cards, tags, workspaces
from app.core.errors import InvalidInput
from app.models import Chunk, EvidenceCard, Paper
from app.workers import ingest

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


async def pdf_less_paper(session, title: str = "No PDF", abstract: str = "An abstract.", **fields) -> Paper:
    """A paper saved without a file, with its abstract as the page-0 chunk (Task 4 makes these for real)."""
    paper = Paper(title=title, abstract=abstract, file_path=None, **fields)
    session.add(paper)
    await session.flush()
    session.add(
        Chunk(
            paper_id=paper.id, ordinal=0, page=0, bbox=[], section_title="Abstract", text=f"{title}. {abstract}",
            embed_model="test", strategy_ver=chunking.STRATEGY_VERSION,
        )
    )  # fmt: skip
    await session.commit()
    await session.refresh(paper)
    return paper


async def chunk_count(session, paper_id) -> int:
    return await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper_id))


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


async def test_file_of_a_paper_without_a_pdf_is_404_no_pdf(client, session):
    paper = await pdf_less_paper(session)
    response = await client.get(f"/api/papers/{paper.id}/file")
    assert (response.status_code, response.json()["detail"]) == (404, "no_pdf")


async def test_deleting_a_paper_without_a_pdf_is_204(client, session):
    paper = await pdf_less_paper(session)
    assert (await client.delete(f"/api/papers/{paper.id}")).status_code == 204
    assert (await client.get(f"/api/papers/{paper.id}")).status_code == 404


async def test_export_for_zotero_skips_only_the_missing_file(client, session, tmp_path):
    ws = (await client.post("/api/workspaces", json={"name": f"Zotero {uuid.uuid4().hex[:6]}"})).json()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    filed = Paper(title="Has a file", file_path=str(pdf), year=2020, authors=["Jane Smith"])
    session.add(filed)
    await session.commit()
    bare = await pdf_less_paper(session, title="Has no file")
    for p in (filed, bare):
        await client.put(f"/api/workspaces/{ws['id']}/papers/{p.id}")
    response = await client.get(f"/api/workspaces/{ws['id']}/citations.zip", params={"format": "bibtex"})
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert sorted(n.rsplit("/", 1)[-1] for n in names if n.startswith("files/")) == ["smith2020has.pdf"]
    refs = zipfile.ZipFile(io.BytesIO(response.content)).read("PaperLab export.bib").decode()
    assert "Has no file" in refs  # still listed in the references, just without an attachment


async def test_ingest_and_rechunk_leave_a_paper_without_a_pdf_alone(worker_session, ctx):
    paper = await pdf_less_paper(worker_session, status="ready")
    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)
    assert (paper.status, paper.status_error, await chunk_count(worker_session, paper.id)) == ("ready", None, 1)


async def test_reingest_refuses_no_pdf(client, session, jobs):
    paper = await pdf_less_paper(session, status="ready")
    response = await client.post(f"/api/papers/{paper.id}/reingest")
    assert (response.status_code, response.json()["detail"]) == (409, "no_pdf")
    await session.refresh(paper)
    assert (paper.status, jobs.jobs) == ("ready", [])  # not flipped to uploaded, nothing queued


async def test_evidence_card_needs_the_full_text(client, session, jobs):
    paper = await pdf_less_paper(session, status="ready")
    response = await client.post(f"/api/papers/{paper.id}/evidence-card")
    assert (response.status_code, response.json()["detail"]) == (422, "needs_full_text")
    assert jobs.jobs == [] and not await session.scalar(select(EvidenceCard).where(EvidenceCard.paper_id == paper.id))
    with pytest.raises(InvalidInput, match="needs_full_text"):
        await evidence_cards.request_cards(session, paper_ids=[paper.id])
    built = await evidence_cards.build_card(session, paper.id)  # the worker path never asks the model either
    assert (built.status, built.error) == ("failed", "needs_full_text")


async def test_generating_missing_cards_skips_papers_without_a_pdf(client, session, jobs, tmp_path):
    ws = (await client.post("/api/workspaces", json={"name": f"Cards {uuid.uuid4().hex[:6]}"})).json()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    filed = Paper(title="Has a file", file_path=str(pdf), status="ready")
    session.add(filed)
    await session.commit()
    bare = await pdf_less_paper(session, status="ready")
    for p in (filed, bare):
        await client.put(f"/api/workspaces/{ws['id']}/papers/{p.id}")
    response = await client.post(f"/api/workspaces/{ws['id']}/evidence-cards")
    assert response.status_code == 202
    assert {r["paper_id"]: r["error"] for r in response.json()}[str(bare.id)] == "needs_full_text"
    assert jobs.jobs == [("generate_evidence_cards", ws["id"], [str(filed.id)])]


async def test_upload_by_doi_onto_a_paper_without_a_pdf_does_not_crash(session, jobs, pdf_dir):
    doi = "10.1234/nopdf"
    paper = await pdf_less_paper(session, doi=doi, status="failed")
    ws = f"NoPdf {uuid.uuid4().hex[:6]}"
    await workspaces.create(session, ws)
    pdf = base64.b64encode(b"%PDF-1.7\n%x\n").decode()
    added = result(await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=pdf, doi=doi))
    assert (added["status"], added["paper_id"]) == ("already_in_library", str(paper.id))
    await session.refresh(paper)
    assert (paper.file_path, jobs.jobs) == (None, [])


async def test_quoting_a_paper_without_a_pdf_says_so_instead_of_crashing(session):
    from app.core import notes
    from app.core.errors import Conflict

    paper = await pdf_less_paper(session, abstract="Sleep helps memory consolidation.")
    with pytest.raises(Conflict, match="no_pdf"):
        await notes.locate_quote(session, paper.id, "Sleep helps memory consolidation.")
