import uuid
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import get_discovery
from app.core import discovery, workspaces
from app.core.candidates import normal_title
from app.core.hit_links import level_of
from app.core.paper_sources import SOURCES, SourceSettings
from app.core.workspace_search import search_batch, snowball
from app.models import Paper
from app.models.provenance import WorkspaceHitLink
from app.models.references import ExternalRef
from app.models.saved_search import SavedSearch
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
async def fake_providers_all(app, fake_providers):
    app.dependency_overrides[get_discovery] = lambda: fake_providers
    yield fake_providers


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


async def test_level_of_terminates_on_a_dense_cyclic_graph(session):
    from app.core.hit_links import level_of

    workspace, run = await _workspace_and_run(session)
    root = await _seed_hit(session, workspace, run)  # has the only search link
    others = []
    for _ in range(5):
        ref = ExternalRef(title=f"dense {uuid.uuid4().hex[:8]}")
        session.add(ref)
        await session.flush()
        hit = WorkspaceSearchHit(
            workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method="snowball_backward",
            normalized_title=uuid.uuid4().hex, first_seen_at=datetime.now(timezone.utc),
        )
        session.add(hit)
        await session.flush()
        others.append(hit)
    everyone = [root, *others]
    for child in everyone:
        for parent in everyone:
            if child.id == parent.id:
                continue
            for kind in ("cites", "cited_by"):
                session.add(WorkspaceHitLink(
                    workspace_id=workspace.id, child_hit_id=child.id, parent_hit_id=parent.id, run_id=run.id,
                    kind=kind,
                ))
    await session.commit()

    assert await level_of(session, root.id) == 0
    assert [await level_of(session, hit.id) for hit in others] == [1] * 5


async def _cluster(session, workspace, run, size, with_root):
    """`size` non-search hits, every ordered pair linked both ways; plus one search root linked from hit 0."""
    hits = []
    for _ in range(size):
        ref = ExternalRef(title=f"dense {uuid.uuid4().hex[:8]}")
        session.add(ref)
        await session.flush()
        hit = WorkspaceSearchHit(
            workspace_id=workspace.id, run_id=run.id, external_ref_id=ref.id, source_method="snowball_backward",
            normalized_title=uuid.uuid4().hex, first_seen_at=datetime.now(timezone.utc),
        )
        session.add(hit)
        hits.append(hit)
    await session.flush()
    session.add_all(
        WorkspaceHitLink(
            workspace_id=workspace.id, child_hit_id=c.id, parent_hit_id=p.id, run_id=run.id, kind=kind
        )
        for c in hits for p in hits if c.id != p.id for kind in ("cites", "cited_by")
    )
    root = None
    if with_root:
        root = await _seed_hit(session, workspace, run)
        session.add(WorkspaceHitLink(
            workspace_id=workspace.id, child_hit_id=hits[0].id, parent_hit_id=root.id, run_id=run.id, kind="cites"
        ))
    await session.commit()
    return hits, root


async def test_level_of_is_fast_on_a_30_node_fully_linked_cluster(session):
    import time

    workspace, run = await _workspace_and_run(session)
    hits, root = await _cluster(session, workspace, run, 30, with_root=True)
    start = time.monotonic()
    levels = [await level_of(session, hit.id) for hit in hits]
    assert levels[0] == 1 and levels[1:] == [2] * 29
    assert await level_of(session, root.id) == 0
    assert time.monotonic() - start < 2


async def test_level_of_a_rootless_cluster_is_legacy_level_zero_and_fast(session):
    import time

    workspace, run = await _workspace_and_run(session)
    hits, _ = await _cluster(session, workspace, run, 30, with_root=False)
    start = time.monotonic()
    assert await level_of(session, hits[0].id) == 0
    assert time.monotonic() - start < 2


def _s2_with(handle):
    return semantic_scholar.new_client(api_key=None, transport=httpx.MockTransport(handle))


async def _stats_of(session, workspace_id):
    run = (
        await session.execute(
            select(WorkspaceSearchRun)
            .where(WorkspaceSearchRun.workspace_id == workspace_id, WorkspaceSearchRun.query_text.like("Snowball%"))
            .order_by(WorkspaceSearchRun.started_at.desc())
        )
    ).scalars().first()
    return run, run.stats_json["snowball"]


async def test_snowball_run_records_seed_stats(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run, title="Seed Alpha")

    await snowball(session, edge_providers, workspace.id, [], [seed.id], backward=True, forward=False)

    snow_run, stats = await _stats_of(session, workspace.id)
    assert snow_run.query_text == 'Snowball from "Seed Alpha"'
    assert stats["directions"] == ["cites"]
    entry = stats["seeds"][0]
    assert (entry["id"], entry["kind"], entry["title"]) == (str(seed.id), "hit", "Seed Alpha")
    assert entry["found"] == {"cites": 1, "cited_by": 0}
    assert entry["new"] == {"cites": 1, "cited_by": 0}
    assert entry["skipped"] is None and entry["error"] is None
    assert entry["errors"] == {"cites": None, "cited_by": None}
    assert entry["done"] == ["cites"] and entry["hit_id"] == str(seed.id)


async def test_partial_failure_records_errors_per_direction(session, fake_providers):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/citations"):
            return httpx.Response(429)
        if request.url.path.endswith("/references"):
            return httpx.Response(200, json={"offset": 0, "data": []})
        return discovery_fake._handle(request)

    client = _s2_with(handle)
    providers = replace(fake_providers, clients={**fake_providers.clients, "semantic_scholar": client})
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run)
    try:
        await snowball(session, providers, workspace.id, [], [seed.id], backward=True, forward=True)
    finally:
        await client.aclose()
    _, stats = await _stats_of(session, workspace.id)
    entry = stats["seeds"][0]
    assert entry["errors"]["cites"] is None and entry["errors"]["cited_by"]
    assert entry["done"] == ["cites"] and entry["error"] == entry["errors"]["cited_by"]


async def test_paper_seed_stats_carry_its_hit_or_none(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    with_hit = Paper(title="Has hit", doi=f"10.5555/h-{uuid.uuid4().hex[:8]}", file_path="/x.pdf")
    bare = Paper(title="No hit", doi=f"10.5555/b-{uuid.uuid4().hex[:8]}", file_path="/y.pdf")
    session.add_all([with_hit, bare])
    await session.flush()
    for paper in (with_hit, bare):
        await workspaces.add_paper(session, workspace.id, paper.id)
    hit = await _seed_hit(session, workspace, run, paper_id=with_hit.id)

    await snowball(session, edge_providers, workspace.id, [with_hit.id, bare.id], [], backward=True, forward=False)

    _, stats = await _stats_of(session, workspace.id)
    assert {e["title"]: e["hit_id"] for e in stats["seeds"]} == {"Has hit": str(hit.id), "No hit": None}


async def test_snowball_query_text_counts_extra_seeds(session, edge_providers):
    workspace, run = await _workspace_and_run(session)
    a = await _seed_hit(session, workspace, run, title="Seed A")
    b = await _seed_hit(session, workspace, run, title="Seed B")

    await snowball(session, edge_providers, workspace.id, [], [a.id, b.id], backward=True, forward=True)

    snow_run, stats = await _stats_of(session, workspace.id)
    assert snow_run.query_text == 'Snowball from "Seed A" and 1 more'
    assert stats["directions"] == ["cites", "cited_by"]


async def test_zero_result_snowball_records_seed_and_error(session, fake_providers):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("/references", "/citations")):
            return httpx.Response(429)
        return discovery_fake._handle(request)

    client = _s2_with(handle)
    providers = replace(fake_providers, clients={**fake_providers.clients, "semantic_scholar": client})
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run, title="Rate limited seed")

    try:
        result = await snowball(session, providers, workspace.id, [], [seed.id], backward=True, forward=True)
    finally:
        await client.aclose()

    assert result.new_hits == 0
    _, stats = await _stats_of(session, workspace.id)
    entry = stats["seeds"][0]
    assert entry["title"] == "Rate limited seed"
    assert entry["found"] == {"cites": 0, "cited_by": 0}
    assert entry["error"]
    assert entry["errors"]["cites"] and entry["errors"]["cited_by"] and entry["done"] == []


async def test_skipped_seed_records_reason(session, fake_providers):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("/references", "/citations")):
            return httpx.Response(404)
        return discovery_fake._handle(request)

    client = _s2_with(handle)
    providers = replace(fake_providers, clients={**fake_providers.clients, "semantic_scholar": client})
    workspace, run = await _workspace_and_run(session)
    seed = await _seed_hit(session, workspace, run, title="Unknown seed")

    try:
        await snowball(session, providers, workspace.id, [], [seed.id], backward=True, forward=False)
    finally:
        await client.aclose()

    _, stats = await _stats_of(session, workspace.id)
    assert stats["seeds"][0]["skipped"] == "not found in Semantic Scholar"


async def test_runs_list_exposes_snowball_stats(session, client, fake_providers_all):
    ws = await client.post("/api/workspaces", json={"name": f"Snowball stats list {uuid.uuid4().hex[:8]}"})
    workspace_id = uuid.UUID(ws.json()["id"])
    free_title, free_doi, _ = discovery_fake.PAPERS[0]
    prior = WorkspaceSearchRun(
        workspace_id=workspace_id, query_text="prior", filters_json={}, query_overrides_json={},
        sources_json=["arxiv"], status="exhausted", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(prior)
    await session.flush()
    ref = ExternalRef(title=free_title, doi=free_doi)
    session.add(ref)
    await session.flush()
    hit = WorkspaceSearchHit(
        workspace_id=workspace_id, run_id=prior.id, external_ref_id=ref.id, source_method="database_search",
        normalized_title=normal_title(free_title), first_seen_at=datetime.now(timezone.utc),
    )
    session.add(hit)
    await session.commit()

    resp = await client.post(
        f"/api/workspaces/{workspace_id}/search/snowball",
        json={"seed_hit_ids": [str(hit.id)], "backward": True, "forward": False},
    )
    assert resp.status_code == 200

    runs = (await client.get(f"/api/workspaces/{workspace_id}/search/runs")).json()
    by_query = {r["query_text"]: r for r in runs}
    assert by_query["prior"]["snowball"] is None
    snow = by_query[f'Snowball from "{free_title}"']["snowball"]
    assert snow["seeds"][0]["title"] == free_title
    assert snow["seeds"][0]["found"]["cites"] > 0
    assert snow["directions"] == ["cites"]


async def _saved_run(session, workspace, saved):
    run = await _run(session, workspace)
    run.saved_search_id = saved.id
    await session.commit()
    return run


async def test_saved_search_repeat_keeps_one_search_link(session, fake_providers):
    workspace, _ = await _workspace_and_run(session)
    saved = SavedSearch(workspace_id=workspace.id, query="bert", schedule="0 6 * * *", timezone="UTC")
    other = SavedSearch(workspace_id=workspace.id, query="gpt", schedule="0 6 * * *", timezone="UTC")
    session.add_all([saved, other])
    await session.flush()
    first = await _saved_run(session, workspace, saved)
    await search_batch(session, fake_providers, first)
    hits = (await session.execute(
        select(WorkspaceSearchHit).where(WorkspaceSearchHit.workspace_id == workspace.id)
    )).scalars().all()
    assert hits

    await search_batch(session, fake_providers, await _saved_run(session, workspace, saved))  # same saved search
    assert len(await _links_of(session, workspace.id)) == len(hits)

    await search_batch(session, fake_providers, await _saved_run(session, workspace, other))  # a different one
    assert len(await _links_of(session, workspace.id)) == 2 * len(hits)
