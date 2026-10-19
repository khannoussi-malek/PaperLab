"""M67: a failed hit whose paper reached the workspace another way is retrieved: imported, linked to that paper."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.core import retrieved_hits, tags, workspaces
from app.core.candidates import normal_title
from app.core.errors import Conflict
from app.core.prisma_export import prisma_export
from app.core.workspace_search import import_hits, upload_hit_pdf
from app.models import Paper, paper_tags, workspace_papers
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import SearchRunEligibility, WorkspaceSearchHit, WorkspaceSearchRun

pytestmark = pytest.mark.anyio

NEURAL = (
    "Neural representations of noncentral events during narrative encoding predict subsequent story ending originality"
)


async def workspace(session, name="M67") -> Workspace:
    ws = Workspace(name=f"{name} {uuid.uuid4().hex[:8]}")
    session.add(ws)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=ws.id, query_text="creativity", filters_json={}, query_overrides_json={}, sources_json=[],
        status="exhausted", started_at=datetime.now(timezone.utc), stats_json={},
    )  # fmt: skip
    session.add(run)
    await session.commit()
    ws.run_id = run.id  # ponytail: one run per test workspace is all these hits need
    return ws


async def failed_hit(session, ws, title=NEURAL, status="failed", **ref_fields) -> WorkspaceSearchHit:
    ref = ExternalRef(title=title, **{"year": 2025, **ref_fields})
    session.add(ref)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=ws.id, run_id=ws.run_id, external_ref_id=ref.id, source_method="database_search",
        stage1_status="relevant", acquisition_status=status, normalized_title=normal_title(title),
        first_seen_at=datetime.now(timezone.utc),
    )  # fmt: skip
    session.add(hit)
    await session.commit()
    return hit


async def paper(session, title=NEURAL, **fields) -> Paper:
    held = Paper(**{"file_path": "/nonexistent.pdf", "title": title, "year": 2025, **fields})
    session.add(held)
    await session.commit()
    return held


async def reload(session, hit) -> WorkspaceSearchHit:
    await session.refresh(hit)
    return hit


async def test_adding_the_paper_to_the_workspace_retrieves_its_failed_hit(session):
    ws = await workspace(session)
    hit = await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")
    held = await paper(session, title="Another title as ingested", doi="10.1126/SCIADV.ADU5251")

    await workspaces.add_paper(session, ws.id, held.id)

    hit = await reload(session, hit)
    assert (hit.acquisition_status, hit.paper_id) == ("imported", held.id)
    ref = await session.get(ExternalRef, hit.external_ref_id)
    await session.refresh(ref)
    assert ref.imported_as == held.id
    assert (await prisma_export(session, ws.id, run_id=None)).not_retrieved == 0


async def test_a_published_doi_on_the_arxiv_copy_retrieves_the_hit(session):
    ws = await workspace(session)
    hit = await failed_hit(session, ws, title="REAL Sampling renamed", doi="10.1162/tacl_a_00757")
    held = await paper(
        session, title="REAL Sampling", doi="10.48550/arxiv.2406.07735", published_doi="10.1162/tacl_a_00757"
    )

    await workspaces.add_paper(session, ws.id, held.id)

    assert (await reload(session, hit)).paper_id == held.id


async def test_the_title_rule_needs_the_year_within_one(session):
    ws = await workspace(session)
    near = await failed_hit(session, ws, title="A Shared Title")
    far = await failed_hit(session, ws, title="A Shared Title: Revisited", year=2019)
    held = await paper(session, title="A shared title", year=2024)
    other = await paper(session, title="A Shared Title: Revisited", year=2025)

    await workspaces.add_paper(session, ws.id, held.id)
    await workspaces.add_paper(session, ws.id, other.id)

    assert (await reload(session, near)).paper_id == held.id
    assert (await reload(session, far)).acquisition_status == "failed"


async def test_an_undated_title_match_is_not_enough(session):
    ws = await workspace(session)
    hit = await failed_hit(session, ws, title="Editorial", year=None)
    held = await paper(session, title="Editorial", year=None)

    await workspaces.add_paper(session, ws.id, held.id)

    assert (await reload(session, hit)).acquisition_status == "failed"


async def test_a_paper_in_another_workspace_leaves_the_hit_alone(session):
    ws, elsewhere = await workspace(session), await workspace(session, "Other")
    hit = await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")
    held = await paper(session, doi="10.1126/sciadv.adu5251")

    await workspaces.add_paper(session, elsewhere.id, held.id)

    assert (await reload(session, hit)).acquisition_status == "failed"


@pytest.mark.parametrize("status", ["not_attempted", "manual"])
async def test_only_failed_hits_change(session, status):
    ws = await workspace(session)
    hit = await failed_hit(session, ws, status=status, doi="10.1126/sciadv.adu5251")
    held = await paper(session, doi="10.1126/sciadv.adu5251")

    await workspaces.add_paper(session, ws.id, held.id)

    hit = await reload(session, hit)
    assert (hit.acquisition_status, hit.paper_id) == (status, None)


async def test_the_repair_links_rows_already_wrong_and_is_idempotent(session):
    ws = await workspace(session)
    held = await paper(session, doi="10.1126/sciadv.adu5251")
    await workspaces.add_paper(session, ws.id, held.id)
    hit = await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")  # failed after the paper arrived
    stays = await failed_hit(session, ws, title="Nobody has this one")

    first = await retrieved_hits.repair(session)
    await session.commit()
    second = await retrieved_hits.repair(session)

    assert hit.id in {f.hit_id for f in first} and stays.id not in {f.hit_id for f in first}
    assert second == []
    assert (await reload(session, hit)).paper_id == held.id
    assert (await reload(session, stays)).acquisition_status == "failed"


async def test_import_hits_counts_a_hit_held_by_title_as_imported(session, discovery_fakes):
    ws = await workspace(session)
    held = await paper(session)
    await workspaces.add_paper(session, ws.id, held.id)
    hit = await failed_hit(session, ws, status="not_attempted")  # no DOI and no PDF link: the download fails

    result = await import_hits(session, discovery_fakes.providers, ws.id, [hit.id])

    assert (result.imported, result.failed) == (1, 0)
    assert (await reload(session, hit)).paper_id == held.id


async def test_an_openalex_id_in_external_ids_retrieves_the_hit(session):
    ws = await workspace(session)
    hit = await failed_hit(session, ws, title="As the hit has it", external_ids={"openalex": "W4400000067"})
    held = await paper(session, title="As the paper has it", openalex_id="W4400000067")

    await workspaces.add_paper(session, ws.id, held.id)

    assert (await reload(session, hit)).paper_id == held.id


async def test_the_refs_published_doi_retrieves_the_hit(session):
    ws = await workspace(session)
    hit = await failed_hit(
        session, ws, title="Preprint title", doi="10.48550/arxiv.2406.07735", published_doi="10.1162/tacl_a_00757"
    )
    held = await paper(session, title="Published title", doi="10.1162/tacl_a_00757")

    await workspaces.add_paper(session, ws.id, held.id)

    assert (await reload(session, hit)).paper_id == held.id


async def test_a_title_match_links_the_hit_but_not_the_shared_reference(session):
    ws = await workspace(session)
    hit = await failed_hit(session, ws)
    held = await paper(session)

    await workspaces.add_paper(session, ws.id, held.id)

    assert (await reload(session, hit)).paper_id == held.id
    ref = await session.get(ExternalRef, hit.external_ref_id)
    await session.refresh(ref)
    assert ref.imported_as is None  # another workspace's hit must not inherit a title guess


async def test_an_ambiguous_title_links_nothing(session):
    ws = await workspace(session)
    for title, year in [("Deep learning", 2015), ("Deep Learning", 2016)]:  # LeCun et al., then Goodfellow et al.
        await workspaces.add_paper(session, ws.id, (await paper(session, title=title, year=year)).id)
    hit = await failed_hit(session, ws, title="Deep Learning", year=2016)  # failed after both arrived

    assert await retrieved_hits.repair(session) == []
    assert (await reload(session, hit)).acquisition_status == "failed"


async def test_the_hits_tags_reach_the_paper_when_it_is_linked(session):
    ws = await workspace(session)
    hit = await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")
    await tags.tag_hits(session, ws.id, ["Q4-cognition"], [hit.id])
    await session.commit()
    held = await paper(session, doi="10.1126/sciadv.adu5251")

    await workspaces.add_paper(session, ws.id, held.id)

    rows = (await session.execute(select(paper_tags.c.tag_id).where(paper_tags.c.paper_id == held.id))).all()
    assert len(rows) == 1


async def test_import_hits_counts_a_hit_linked_inside_the_batch(session, discovery_fakes, pdf_dir):
    ws = await workspace(session)
    discovery_fakes.pdf_host.reply("/ok.pdf", 200, content=b"%PDF-1.4 ok")
    no_pdf = await failed_hit(session, ws, status="not_attempted")
    with_pdf = await failed_hit(session, ws, status="not_attempted", pdf_urls=["https://pdf.example/ok.pdf"])

    result = await import_hits(session, discovery_fakes.providers, ws.id, [no_pdf.id, with_pdf.id])

    assert (result.imported, result.failed) == (2, 0)
    assert (await reload(session, no_pdf)).paper_id == (await reload(session, with_pdf)).paper_id


async def test_the_dry_run_names_each_link_and_its_rule(session):
    ws = await workspace(session)
    held = await paper(session, doi="10.1126/sciadv.adu5251")
    await workspaces.add_paper(session, ws.id, held.id)
    await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")

    [found] = await retrieved_hits.repair(session)

    assert (found.paper_id, found.rule) == (held.id, "identifier")


# --- M73: a research-run import reuses a held published version or arXiv copy instead of duplicating it ---

REAL = "REAL Sampling: Boosting Factuality and Diversity of Open-Ended Generation via Asymptotic Entropy"
AUTHORS = ["Haw-Shiuan Chang", "Nanyun Peng", "Mohit Bansal"]
TACL = "10.1162/tacl_a_00757"
ARXIV_DOI = "10.48550/arxiv.2406.07735"


async def test_import_reuses_the_held_published_version_of_an_arxiv_hit(session, discovery_fakes):
    ws = await workspace(session)
    held = await paper(session, title=REAL, authors=AUTHORS, year=2025, doi=TACL, source_type="journal_article")
    hit = await failed_hit(
        session, ws, title=REAL, status="not_attempted", authors=AUTHORS, year=2024, doi=ARXIV_DOI,
        external_ids={"arxiv": "2406.07735"}, pdf_urls=["https://pdf.example/pdf/2406.07735"],
    )  # fmt: skip

    result = await import_hits(session, discovery_fakes.providers, ws.id, [hit.id])

    assert (result.imported, result.failed, result.paper_ids) == (1, 0, [])
    assert (await reload(session, hit)).paper_id == held.id
    assert held.id in [p.id for p in await workspaces.papers(session, ws.id)]
    assert discovery_fakes.pdf_host.requests == []  # nothing downloaded
    ref = await session.get(ExternalRef, hit.external_ref_id)
    await session.refresh(ref)
    assert ref.imported_as is None  # a title match never claims the shared reference (M67)


async def test_import_reuses_the_held_arxiv_copy_of_a_publisher_hit(session, discovery_fakes):
    ws = await workspace(session)
    held = await paper(session, title=REAL, authors=AUTHORS, year=2024, doi=ARXIV_DOI, source_type="preprint")
    hit = await failed_hit(
        session, ws, title=REAL, status="not_attempted", authors=AUTHORS, year=2025, doi=TACL,
        venue="Transactions of the Association for Computational Linguistics", external_ids={"arxiv": "2406.07735"},
        pdf_urls=["https://pdf.example/closed"],
    )  # fmt: skip

    result = await import_hits(session, discovery_fakes.providers, ws.id, [hit.id])

    assert (result.imported, result.paper_ids) == (1, [])
    assert (await reload(session, hit)).paper_id == held.id
    ref = await session.get(ExternalRef, hit.external_ref_id)
    await session.refresh(ref)
    assert ref.imported_as == held.id  # matched by its arXiv id: an identifier, so the reference may say so


async def test_import_still_downloads_a_lookalike_by_other_authors(session, discovery_fakes, pdf_dir):
    ws = await workspace(session)
    held = await paper(
        session, title=REAL, authors=["Someone Else"], year=2025, doi=TACL, source_type="journal_article"
    )
    discovery_fakes.pdf_host.reply("/pdf/2406.07735", 200, content=b"%PDF-1.4 lookalike")
    hit = await failed_hit(
        session, ws, title=REAL, status="not_attempted", authors=AUTHORS, year=2024, doi=ARXIV_DOI,
        external_ids={"arxiv": "2406.07735"}, pdf_urls=["https://pdf.example/pdf/2406.07735"],
    )  # fmt: skip

    result = await import_hits(session, discovery_fakes.providers, ws.id, [hit.id])

    assert result.imported == 1 and len(result.paper_ids) == 1
    assert (await reload(session, hit)).paper_id not in (None, held.id)


async def test_a_held_publisher_paper_wins_and_its_held_arxiv_duplicate_is_left_alone(session, discovery_fakes):
    ws = await workspace(session)
    publisher = await paper(session, title=REAL, authors=AUTHORS, year=2025, doi=TACL, source_type="journal_article")
    arxiv = await paper(session, title=REAL, authors=AUTHORS, year=2024, doi=ARXIV_DOI, source_type="preprint")
    hit = await failed_hit(
        session, ws, title=REAL, status="not_attempted", authors=AUTHORS, year=2025, doi=TACL,
        external_ids={"arxiv": "2406.07735"}, pdf_urls=["https://pdf.example/closed"],
    )  # fmt: skip

    await import_hits(session, discovery_fakes.providers, ws.id, [hit.id])

    assert (await reload(session, hit)).paper_id == publisher.id  # the DOI match wins
    await session.refresh(arxiv)
    assert arxiv.published_doi is None  # two papers must not both answer to the TACL DOI


async def test_link_marks_a_failed_hit_awaiting_pdf_when_its_match_has_no_pdf(session):
    ws = await workspace(session)
    held = await paper(session, doi="10.1126/sciadv.adu5251", file_path=None)
    hit = await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")

    await workspaces.add_paper(session, ws.id, held.id)  # link runs on this

    hit = await reload(session, hit)
    assert (hit.acquisition_status, hit.paper_id) == ("awaiting_pdf", held.id)


async def test_import_hits_links_a_pdfless_holder_as_awaiting_pdf(session, discovery_fakes):
    ws = await workspace(session)
    held = await paper(session, doi="10.1126/sciadv.adu5251", file_path=None)
    hit = await failed_hit(session, ws, status="not_attempted", doi="10.1126/sciadv.adu5251")

    result = await import_hits(session, discovery_fakes.providers, ws.id, [hit.id])

    hit = await reload(session, hit)
    assert (hit.acquisition_status, hit.paper_id) == ("awaiting_pdf", held.id)
    assert (result.imported, result.failed, result.paper_ids) == (0, 1, [])
    members = await session.scalars(select(workspace_papers.c.paper_id).where(workspace_papers.c.workspace_id == ws.id))
    assert members.all() == [held.id]


async def test_awaiting_pdf_counts_as_not_retrieved(session):
    ws = await workspace(session)
    held = await paper(session, file_path=None)
    await failed_hit(session, ws, status="awaiting_pdf")
    await workspaces.add_paper(session, ws.id, held.id)

    prisma = await prisma_export(session, ws.id, run_id=None)

    assert (prisma.sought, prisma.not_retrieved) == (1, 1)


async def test_an_unread_paper_never_counts_as_assessed_or_included(session):
    """R9: an eligibility row counts only when its paper has a PDF and its hit is retrieved, even one written
    straight to the table."""
    ws = await workspace(session)
    read = await paper(session, title="Read")
    awaiting = await paper(session, title="Awaiting", file_path=None)
    unread = await paper(session, title="Marked imported, no PDF", file_path=None)
    for held, status in ((read, "imported"), (awaiting, "awaiting_pdf"), (unread, "imported")):
        hit = await failed_hit(session, ws, title=held.title, status=status)
        hit.paper_id = held.id
        await workspaces.add_paper(session, ws.id, held.id)
        session.add(SearchRunEligibility(
            paper_id=held.id, search_run_id=ws.run_id, stage2_status="include", assessed_at=datetime.now(timezone.utc),
        ))  # fmt: skip
    await session.commit()

    prisma = await prisma_export(session, ws.id, run_id=None)

    assert (prisma.not_retrieved, prisma.stage2_assessed, prisma.included) == (1, 1, 1)


async def test_an_upload_for_a_hit_whose_paper_has_no_pdf_is_refused_not_discarded(session):
    ws = await workspace(session)
    twin = await paper(session, file_path=None)
    hit = await failed_hit(session, ws, status="not_attempted", imported_as=twin.id)

    with pytest.raises(Conflict, match="paper_has_no_pdf"):
        await upload_hit_pdf(session, ws.id, hit.id, "a.pdf", b"%PDF-1.7 mine")

    assert (await reload(session, hit)).acquisition_status == "not_attempted"


async def test_an_upload_for_a_hit_whose_doi_a_pdfless_paper_holds_creates_nothing(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pdf_dir", tmp_path)  # so a wrongly created paper fails the assert, not the disk
    ws = await workspace(session)  # the hit has no imported_as: Find papers saved the paper without it
    held = await paper(session, doi="10.1126/sciadv.adu5251", file_path=None)
    await workspaces.add_paper(session, ws.id, held.id)
    hit = await failed_hit(session, ws, doi="10.1126/sciadv.adu5251")

    with pytest.raises(Conflict, match="paper_has_no_pdf"):
        await upload_hit_pdf(session, ws.id, hit.id, "a.pdf", b"%PDF-1.7 mine")

    assert len((await session.scalars(select(Paper))).all()) == 1
    assert (await reload(session, hit)).acquisition_status == "failed"
