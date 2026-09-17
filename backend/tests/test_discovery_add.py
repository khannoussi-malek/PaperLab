import pytest
from sqlalchemy import select

from app.core import discovery, enrichment
from app.core.discovery import Candidate
from app.core.errors import Conflict
from app.models import Paper, PaperStatus
from app.workers import ingest

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.7\n%a found paper\n"
HOST = "https://pdf.example"


def candidate(**fields) -> Candidate:
    return Candidate(**{"title": "Found: A Paper / Part 2", "authors": ["Ada Lovelace"], "year": 2024, **fields})


async def test_the_first_url_whose_body_is_a_pdf_wins(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/landing", 200, text="<html>a landing page</html>")
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)
    discovery_fakes.pdf_host.reply("/later.pdf", 200, content=PDF)
    found = candidate(
        openalex_id="W9000000003",
        doi="10.5555/m19-found",
        venue="Proceedings of Tests",
        cited_by_count=7,
        pdf_urls=[f"{HOST}/landing", f"{HOST}/copy.pdf", f"{HOST}/later.pdf"],
    )

    paper = await discovery.add(session, discovery_fakes.providers, found, pdf_dir)

    assert [r.url.path for r in discovery_fakes.pdf_host.requests] == ["/landing", "/copy.pdf"]
    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF
    assert (paper.title, paper.authors, paper.year, paper.venue, paper.cited_by_count) == (
        "Found: A Paper / Part 2", ["Ada Lovelace"], 2024, "Proceedings of Tests", 7,
    )  # fmt: skip
    assert (paper.openalex_id, paper.doi, paper.manual_fields) == ("W9000000003", "10.5555/m19-found", ["title"])
    assert paper.status == PaperStatus.UPLOADED


async def test_a_paper_found_without_openalex_locks_its_doi_so_enrichment_trusts_it(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)

    by_doi = await discovery.add(
        session, discovery_fakes.providers, candidate(doi="10.5555/m19-s2", pdf_urls=[f"{HOST}/copy.pdf"]), pdf_dir
    )
    by_arxiv = await discovery.add(
        session, discovery_fakes.providers, candidate(arxiv_id="2003.07000", pdf_urls=[f"{HOST}/copy.pdf"]), pdf_dir
    )

    assert (by_doi.doi, by_doi.openalex_id, by_doi.manual_fields) == ("10.5555/m19-s2", None, ["doi", "title"])
    assert (by_arxiv.doi, by_arxiv.manual_fields) == ("10.48550/arxiv.2003.07000", ["doi", "title"])


async def test_no_free_pdf_stores_nothing(session, discovery_fakes, pdf_dir, monkeypatch):
    monkeypatch.setattr(discovery, "MAX_PDF_BYTES", len(PDF) - 1)
    discovery_fakes.pdf_host.reply("/landing", 200, text="<html>a landing page</html>")
    discovery_fakes.pdf_host.reply("/gone.pdf", 404, text="not found")
    discovery_fakes.pdf_host.refuse("/down.pdf")
    discovery_fakes.pdf_host.reply("/huge.pdf", 200, content=PDF)
    urls = [f"{HOST}/landing", f"{HOST}/gone.pdf", f"{HOST}/down.pdf", f"{HOST}/huge.pdf"]

    with pytest.raises(Conflict, match="No free PDF was found"):
        await discovery.add(
            session, discovery_fakes.providers, candidate(doi="10.5555/m19-none", pdf_urls=urls), pdf_dir
        )

    assert len(discovery_fakes.pdf_host.requests) == 4
    assert not pdf_dir.exists() or not any(pdf_dir.iterdir())
    assert (await session.scalars(select(Paper).where(Paper.doi == "10.5555/m19-none"))).all() == []


async def test_a_candidate_with_no_urls_has_no_free_pdf(session, discovery_fakes, pdf_dir):
    with pytest.raises(Conflict, match="No free PDF was found"):
        await discovery.add(session, discovery_fakes.providers, candidate(), pdf_dir)


async def test_a_paper_already_in_the_library_is_refused_before_any_download(session, discovery_fakes, pdf_dir):
    session.add(Paper(title="Owned", file_path="/nonexistent.pdf", doi="10.5555/m19-owned"))
    await session.flush()

    with pytest.raises(Conflict, match="already in your library"):
        await discovery.add(
            session,
            discovery_fakes.providers,
            candidate(doi="10.5555/M19-Owned", pdf_urls=[f"{HOST}/copy.pdf"]),
            pdf_dir,
        )
    assert discovery_fakes.pdf_host.requests == []


async def test_a_redirect_to_the_pdf_is_followed(session, discovery_fakes, pdf_dir):
    discovery_fakes.pdf_host.reply("/abs", 302, headers={"location": f"{HOST}/copy.pdf"})
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=PDF)

    paper = await discovery.add(session, discovery_fakes.providers, candidate(pdf_urls=[f"{HOST}/abs"]), pdf_dir)

    assert (pdf_dir / f"{paper.id}.pdf").read_bytes() == PDF


async def test_a_found_papers_title_survives_ingest_and_still_takes_a_hand_correction(
    worker_session, discovery_fakes, pdf_dir, sample_pdf, ctx
):
    """M7.5 bug: _prefill wrote candidate.title but not manual_fields, so ingest's font heuristic (sample_pdf's own
    "Deep Paper Title") overwrote it at extraction. The source's title must survive both ingest and enrichment, and
    still be replaceable by a hand correction."""
    discovery_fakes.pdf_host.reply("/copy.pdf", 200, content=sample_pdf.read_bytes())
    found = candidate(title="Semantic Similarity in a Taxonomy", pdf_urls=[f"{HOST}/copy.pdf"])

    paper = await discovery.add(worker_session, discovery_fakes.providers, found, pdf_dir)
    assert "title" in paper.manual_fields

    await ingest.ingest_paper(ctx, str(paper.id))
    await worker_session.refresh(paper)
    assert paper.status == "ready" and paper.title == "Semantic Similarity in a Taxonomy"

    corrected = await enrichment.correct_metadata(worker_session, paper.id, {"title": "Hand-Corrected Title"})
    assert corrected.title == "Hand-Corrected Title"
