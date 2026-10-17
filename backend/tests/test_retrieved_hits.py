"""M67: a failed hit whose paper reached the workspace another way is retrieved: imported, linked to that paper."""

import uuid
from datetime import datetime, timezone

import pytest

from app.core import retrieved_hits, workspaces
from app.core.candidates import normal_title
from app.core.prisma_export import prisma_export
from app.core.workspace_search import import_hits
from app.models import Paper
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

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
    held = Paper(file_path="/nonexistent.pdf", title=title, **{"year": 2025, **fields})
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

    assert hit.id in first and stays.id not in first
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
