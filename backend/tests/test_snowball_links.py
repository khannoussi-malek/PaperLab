import uuid
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core import discovery, workspaces
from app.core.candidates import normal_title
from app.core.hit_links import level_of
from app.core.paper_sources import SOURCES, SourceSettings
from app.core.workspace_search import search_batch, snowball
from app.models import Paper
from app.models.provenance import WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import discovery_fake, semantic_scholar

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]


@pytest.fixture
async def fake_providers():
    every_source = SourceSettings(contact_email=discovery_fake.MAILTO, enabled=dict.fromkeys(SOURCES, True))
    providers = discovery.build_providers(every_source, discovery_fake.transport())
    yield providers
    await providers.aclose()


@pytest.fixture
async def edge_providers(fake_providers):
    """Providers whose S2 answers /references and /citations with a distinct, per-test paper each."""
    tag = uuid.uuid4().hex[:8]

    def s2_paper(prefix: str) -> dict:
        return {
            "paperId": uuid.uuid4().hex + "0" * 8, "title": f"{prefix} {tag}", "year": 2026, "venue": "J",
            "authors": [{"name": "Ada"}], "externalIds": {"DOI": f"10.5555/{prefix}-{tag}"},
            "openAccessPdf": {"url": ""}, "citationCount": 1,
        }

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/references"):
            return httpx.Response(200, json={"offset": 0, "data": [{"citedPaper": s2_paper("ref")}]})
        if path.endswith("/citations"):
            return httpx.Response(200, json={"offset": 0, "data": [{"citingPaper": s2_paper("cit")}]})
        return discovery_fake._handle(request)

    client = semantic_scholar.new_client(api_key=None, transport=httpx.MockTransport(handle))
    yield replace(fake_providers, clients={**fake_providers.clients, "semantic_scholar": client})
    await client.aclose()


async def _workspace_and_run(session, sources=("arxiv",)):
    workspace = Workspace(name=f"links-{uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = await _run(session, workspace, sources)
    return workspace, run


async def _run(session, workspace, sources=("arxiv",)):
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="bert", filters_json={}, query_overrides_json={},
        sources_json=list(sources), status="running", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    for source in sources:
        session.add(WorkspaceSearchCursor(run_id=run.id, source=source, cursor_json={"value": 0}))
    await session.commit()
    return run


async def _seed_hit(session, workspace, run, *, paper_id=None, title=None, doi=None):
    title = title or f"Seed {uuid.uuid4().hex[:8]}"
    ref = ExternalRef(title=title, doi=doi or f"10.5555/seed-{uuid.uuid4().hex[:8]}")
    session.add(ref)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method="database_search",
        paper_id=paper_id, normalized_title=normal_title(title), first_seen_at=datetime.now(timezone.utc),
    )
    session.add(hit)
    await session.flush()
    session.add(WorkspaceHitLink(workspace_id=workspace.id, child_hit_id=hit.id, run_id=run.id, kind="search"))
    await session.commit()
    return hit


async def _links_of(session, workspace_id, **where):
    rows = await session.execute(select(WorkspaceHitLink).where(WorkspaceHitLink.workspace_id == workspace_id))
    return [link for link in rows.scalars() if all(getattr(link, k) == v for k, v in where.items())]


async def _hit_by_id(session, hit_id):
    return await session.get(WorkspaceSearchHit, hit_id)


async def test_search_batch_writes_search_links(session, fake_providers):
    workspace, run = await _workspace_and_run(session)
    await search_batch(session, fake_providers, run)

    rows = await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id))
    hits = rows.scalars().all()
    assert hits
    links = await _links_of(session, workspace.id)
    assert sorted(link.child_hit_id for link in links) == sorted(h.id for h in hits)
    assert all(link.kind == "search" and link.run_id == run.id and link.parent_hit_id is None for link in links)


async def test_refound_hit_gains_link_keeps_decision(session, fake_providers):
    workspace, run1 = await _workspace_and_run(session)
    await search_batch(session, fake_providers, run1)
    hit = (await session.execute(
        select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace.id).limit(1)
    )).scalars().one()
    hit.stage1_status = "relevant"
    await session.commit()
    before = (await session.execute(
        select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace.id)
    )).scalars().all()

    run2 = await _run(session, workspace)
    await search_batch(session, fake_providers, run2)

    after = (await session.execute(
        select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace.id)
    )).scalars().all()
    assert len(after) == len(before)
    await session.refresh(hit)
    assert hit.stage1_status == "relevant"
    assert {link.run_id for link in await _links_of(session, workspace.id, child_hit_id=hit.id)} == {run1.id, run2.id}


async def test_snowball_from_hit_links_parent_and_level(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run)

    result = await snowball(session, edge_providers, workspace.id, [], [seed.id], backward=True, forward=False)
    assert result.new_hits == 1
    links = await _links_of(session, workspace.id, parent_hit_id=seed.id)
    assert [(link.kind, link.parent_paper_id) for link in links] == [("cites", None)]
    child = await _hit_by_id(session, links[0].child_hit_id)
    assert child.snowball_round == 1
    assert await level_of(session, seed.id) == 0 and await level_of(session, child.id) == 1

    result = await snowball(session, edge_providers, workspace.id, [], [child.id], backward=False, forward=True)
    assert result.new_hits == 1
    grand_links = await _links_of(session, workspace.id, parent_hit_id=child.id)
    assert [link.kind for link in grand_links] == ["cited_by"]
    assert (await _hit_by_id(session, grand_links[0].child_hit_id)).snowball_round == 2


async def test_snowball_from_imported_paper_attaches_to_its_hit(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    paper = Paper(title="Imported seed", doi=f"10.5555/imp-{uuid.uuid4().hex[:8]}", file_path="/nonexistent.pdf")
    session.add(paper)
    await session.flush()
    await workspaces.add_paper(session, workspace.id, paper.id)
    hit = await _seed_hit(session, workspace, run, paper_id=paper.id)

    await snowball(session, edge_providers, workspace.id, [paper.id], [], backward=False, forward=True)

    links = await _links_of(session, workspace.id, kind="cited_by")
    assert len(links) == 1 and links[0].parent_hit_id == hit.id and links[0].parent_paper_id is None
    assert (await _hit_by_id(session, links[0].child_hit_id)).snowball_round == 1


async def test_snowball_from_hand_added_paper_uses_parent_paper(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    paper = Paper(title="Hand-added seed", doi=f"10.5555/hand-{uuid.uuid4().hex[:8]}", file_path="/nonexistent.pdf")
    session.add(paper)
    await session.flush()
    await workspaces.add_paper(session, workspace.id, paper.id)

    await snowball(session, edge_providers, workspace.id, [paper.id], [], backward=True, forward=False)

    links = await _links_of(session, workspace.id, kind="cites")
    assert len(links) == 1 and links[0].parent_hit_id is None and links[0].parent_paper_id == paper.id
    child = await _hit_by_id(session, links[0].child_hit_id)
    assert child.snowball_round == 1 and await level_of(session, child.id) == 1


async def test_snowball_links_existing_pool_hit(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run)
    first = await snowball(session, edge_providers, workspace.id, [], [seed.id], backward=True, forward=False)
    assert first.new_hits == 1
    child_id = (await _links_of(session, workspace.id, parent_hit_id=seed.id))[0].child_hit_id
    # A second seed whose reference is that same pool hit: the handler's references are per-fixture, so reuse the
    # child's ref by snowballing the child's own sibling seed through a transport that answers the same paper.
    other = await _seed_hit(session, workspace, run)
    child_ref = await session.get(ExternalRef, (await _hit_by_id(session, child_id)).external_ref_id)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/references"):
            paper = {
                "paperId": "c" * 40, "title": child_ref.title, "year": 2026, "venue": "J", "authors": [],
                "externalIds": {"DOI": child_ref.doi}, "openAccessPdf": {"url": ""}, "citationCount": 1,
            }
            return httpx.Response(200, json={"offset": 0, "data": [{"citedPaper": paper}]})
        return discovery_fake._handle(request)

    client = semantic_scholar.new_client(api_key=None, transport=httpx.MockTransport(handle))
    providers = replace(edge_providers, clients={**edge_providers.clients, "semantic_scholar": client})
    try:
        second = await snowball(session, providers, workspace.id, [], [other.id], backward=True, forward=False)
    finally:
        await client.aclose()

    assert second.new_hits == 0
    links = await _links_of(session, workspace.id, child_hit_id=child_id)
    assert {link.parent_hit_id for link in links} == {seed.id, other.id}
