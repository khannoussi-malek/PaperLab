import uuid
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.core import discovery
from app.core.candidates import Candidate, normal_title
from app.core.paper_sources import SOURCES, SourceSettings
from app.core.workspace_search import _find_or_create_external_ref, _insert_hit, search_batch
from app.models.references import ExternalRef
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun
from app.providers import arxiv, discovery_fake

pytestmark = pytest.mark.anyio

# Task 2's cursor convention (task-2-brief.md): 0 for arXiv/CORE/Crossref/S2 (offset-style), 1 for OpenAlex
# (1-based page number). Starting OpenAlex at 0 would ask its fake for a negative offset and get nothing back.
START_CURSOR = {"arxiv": 0, "semantic_scholar": 0, "openalex": 1, "unpaywall": 0}


@pytest.fixture
async def fake_providers():
    """Every source on, routed to discovery_fake's real MockTransport — same pattern as test_discovery_fake.py's own
    `fake_providers` fixture. search_batch's merge/dedup then runs against the real fake provider (Task 11's
    PAGE_PAPERS fixture), not a hand-rolled mock of provider responses."""
    every_source = SourceSettings(contact_email=discovery_fake.MAILTO, enabled=dict.fromkeys(SOURCES, True))
    providers = discovery.build_providers(every_source, discovery_fake.transport())
    yield providers
    await providers.aclose()


async def _new_run(session, sources: list[str]) -> WorkspaceSearchRun:
    workspace = Workspace(name=f"Engine test {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id,
        query_text="bert",
        filters_json={},
        query_overrides_json={},
        sources_json=sources,
        status="running",
        started_at=datetime.now(timezone.utc),
        stats_json={},
    )
    session.add(run)
    await session.flush()
    for source in sources:
        session.add(WorkspaceSearchCursor(run_id=run.id, source=source, cursor_json={"value": START_CURSOR[source]}))
    await session.commit()
    return run


async def test_search_batch_creates_hits_and_advances_cursors(session, fake_providers):
    run = await _new_run(session, ["arxiv"])

    result = await search_batch(session, fake_providers, run)

    assert result.new_hits >= 1
    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id))).scalars().all()
    )
    assert len(hits) == result.new_hits
    assert all(h.acquisition_status == "not_attempted" for h in hits)

    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "arxiv"
            )
        )
    ).scalar_one()
    assert cursor.exhausted  # PAGE_SIZE_BY_SOURCE["arxiv"] (20) exceeds the fixture's 3-item page


async def test_search_batch_dedupes_across_sources(session, fake_providers):
    # discovery_fake's PAGE_PAPERS fixture answers the same 3 papers (shared DOIs) from every source; the merge
    # step (reusing candidates.merge/_same_paper) must collapse them to one hit per paper, not one per source.
    run = await _new_run(session, ["arxiv", "semantic_scholar", "openalex"])

    result = await search_batch(session, fake_providers, run)

    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.run_id == run.id))).scalars().all()
    )
    titles = {h.normalized_title for h in hits}
    assert len(titles) == len(hits)  # no duplicate normalized titles from the same fixture paper
    assert len(hits) == 3  # 3 sources x 3 shared papers, merged down to 3 — not 9
    assert result.new_hits == 3


async def test_search_batch_preserves_existing_screening_state(session, fake_providers):
    # discovery_fake's PAGE_PAPERS[0] ("...Fixture 1", doi "...page-1") is what arxiv's page 0 returns first.
    # Pre-seed its ExternalRef + a WorkspaceSearchHit already screened by a user (this run's spec P2's global
    # constraint: a hit already in the pool — this run or an earlier one — keeps its screening state).
    run = await _new_run(session, ["arxiv"])
    title, doi = discovery_fake.PAGE_PAPERS[0]
    ref = ExternalRef(title=title, doi=doi)
    session.add(ref)
    await session.flush()
    existing_hit = WorkspaceSearchHit(
        workspace_id=run.workspace_id,
        run_id=run.id,
        external_ref_id=ref.id,
        source_method="database_search",
        normalized_title=normal_title(title),
        first_seen_at=datetime.now(timezone.utc),
        stage1_status="relevant",
        priority=2,
    )
    session.add(existing_hit)
    await session.commit()

    result = await search_batch(session, fake_providers, run)

    hits = (
        (await session.execute(select(WorkspaceSearchHit).where(WorkspaceSearchHit.external_ref_id == ref.id)))
        .scalars()
        .all()
    )
    assert len(hits) == 1  # not duplicated by this batch
    assert hits[0].id == existing_hit.id
    assert hits[0].stage1_status == "relevant"  # untouched, not overwritten or reset
    assert hits[0].priority == 2
    assert result.new_hits == 2  # the other 2 PAGE_PAPERS are still new


async def test_search_batch_records_source_error_without_failing_run(session, fake_providers):
    broken_arxiv = arxiv.new_client(httpx.MockTransport(lambda request: httpx.Response(429)))
    providers = replace(fake_providers, arxiv=broken_arxiv)
    run = await _new_run(session, ["arxiv"])

    try:
        result = await search_batch(session, providers, run)
    finally:
        await broken_arxiv.aclose()

    assert "arxiv" in result.errors
    assert result.new_hits == 0
    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "arxiv"
            )
        )
    ).scalar_one()
    assert cursor.last_error is not None
    assert not cursor.exhausted


async def test_search_batch_skips_a_cooling_down_source_without_counting_a_new_error(session, fake_providers, monkeypatch):
    """A source that just errored is skipped entirely on the very next call, not retried immediately — real
    consecutive-iteration retries land within a couple of pacing intervals of each other (a few seconds), which
    doesn't give a brief/transient error (arXiv's API has answered a plain 406 to an otherwise-valid, identical
    request that then succeeded seconds later) any real chance to clear before the source is abandoned."""
    from app.core import workspace_search as core_module

    fails_once = [True]

    async def flaky_arxiv_search(http, query, page_size, cursor):
        if fails_once[0]:
            fails_once[0] = False
            raise httpx.HTTPError("transient 406")
        return [], None

    monkeypatch.setitem(core_module._PAGE_FUNCS, "arxiv", flaky_arxiv_search)
    fake_clock = iter([datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)])
    monkeypatch.setattr(core_module, "_now", lambda: next(fake_clock))

    run = await _new_run(session, ["arxiv"])
    await search_batch(session, fake_providers, run)  # first call: errors, starts a 10s cooldown
    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "arxiv"
            )
        )
    ).scalar_one()
    assert cursor.cursor_json["errors"] == 1

    # Second call, one fake second later — still well inside the cooldown. Must be skipped entirely: no new
    # attempt (flaky_arxiv_search would raise AssertionError-free either way here, so the real signal is the
    # error count staying put, not incrementing to 2).
    result = await search_batch(session, fake_providers, run)
    await session.refresh(cursor)
    assert "arxiv" not in result.errors
    assert cursor.cursor_json["errors"] == 1
    assert not cursor.exhausted


async def test_search_batch_retries_a_cooled_down_source_and_a_success_clears_the_error_count(session, fake_providers, monkeypatch):
    """Once the cooldown has genuinely elapsed, the source is tried again — and a page that succeeds this time
    clears the error streak entirely (same as a fresh cursor), not just decrements it."""
    from app.core import workspace_search as core_module

    fails_once = [True]

    async def flaky_arxiv_search(http, query, page_size, cursor):
        if fails_once[0]:
            fails_once[0] = False
            raise httpx.HTTPError("transient 406")
        return [], None  # succeeds and exhausts cleanly on the retry

    monkeypatch.setitem(core_module._PAGE_FUNCS, "arxiv", flaky_arxiv_search)
    far_future = iter([datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, 1, tzinfo=timezone.utc)])
    monkeypatch.setattr(core_module, "_now", lambda: next(far_future))

    run = await _new_run(session, ["arxiv"])
    await search_batch(session, fake_providers, run)  # errors, starts a cooldown

    result = await search_batch(session, fake_providers, run)  # an hour later: well past even the longest backoff

    assert "arxiv" not in result.errors
    assert result.sources_exhausted == ["arxiv"]  # the retry ran (not skipped) and succeeded straight to exhaustion
    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "arxiv"
            )
        )
    ).scalar_one()
    assert cursor.exhausted  # this fake's next_cursor is None — a real, clean exhaustion, not an error-cap trip
    assert cursor.last_error is None  # cleared unconditionally on any successful page, exhausting or not


async def test_search_batch_marks_a_disabled_source_cursor_exhausted(session):
    """A source whose Providers.client() is None (Unpaywall with no contact_email configured — the
    fresh-database default) has nothing to fetch. Its cursor must still flip to exhausted immediately, or the
    worker's `all(c.exhausted for c in cursors)` check can never become true (M30a Task 17 E2E bug: a source
    stuck at exhausted=False forever turns the worker's paging loop into a busy-loop)."""
    providers = discovery.Providers(pdf=httpx.AsyncClient())  # every other client left at its None default
    try:
        run = await _new_run(session, ["unpaywall"])
        result = await search_batch(session, providers, run)
    finally:
        await providers.pdf.aclose()

    assert result.new_hits == 0
    cursor = (
        await session.execute(
            select(WorkspaceSearchCursor).where(
                WorkspaceSearchCursor.run_id == run.id, WorkspaceSearchCursor.source == "unpaywall"
            )
        )
    ).scalar_one()
    assert cursor.exhausted
    assert cursor.last_error is None  # not an error state — there was nothing to do here


@pytest.mark.asyncio
async def test_start_run_creates_cursors_for_each_source(session):
    from app.core.workspace_search import start_run
    workspace = Workspace(name=f"Lifecycle {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()

    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv", "openalex"])

    assert run.status == "running"
    cursors = (await session.execute(
        select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    )).scalars().all()
    assert {c.source for c in cursors} == {"arxiv", "openalex"}


@pytest.mark.asyncio
async def test_stop_run_sets_status_and_stopped_at(session):
    from app.core.workspace_search import start_run, stop_run
    workspace = Workspace(name=f"Stop {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"])

    stopped = await stop_run(session, run.id)

    assert stopped.status == "stopped"
    assert stopped.stopped_at is not None


@pytest.mark.asyncio
async def test_start_run_on_a_stopped_run_resumes_its_cursors(session):
    from app.core.workspace_search import start_run, stop_run
    workspace = Workspace(name=f"Resume {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"])
    cursor = (await session.execute(
        select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    )).scalar_one()
    cursor.cursor_json = {"value": 40}
    await session.commit()
    await stop_run(session, run.id)

    resumed = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"], run_id=run.id)

    assert resumed.id == run.id
    assert resumed.status == "running"
    reloaded_cursor = (await session.execute(
        select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id)
    )).scalar_one()
    assert reloaded_cursor.cursor_json == {"value": 40}


@pytest.mark.asyncio
async def test_start_run_raises_conflict_on_already_running(session):
    from app.core.errors import Conflict
    from app.core.workspace_search import start_run
    workspace = Workspace(name=f"Conflict {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"])

    with pytest.raises(Conflict):
        await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"], run_id=run.id)


@pytest.mark.asyncio
async def test_start_run_raises_not_found_for_cross_workspace_run(session):
    from app.core.errors import NotFound
    from app.core.workspace_search import start_run, stop_run
    workspace_a = Workspace(name=f"Workspace A {uuid.uuid4().hex[:8]}")
    workspace_b = Workspace(name=f"Workspace B {uuid.uuid4().hex[:8]}")
    session.add(workspace_a)
    session.add(workspace_b)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace_a.id, "bert", filters={}, sources=["arxiv"])
    await stop_run(session, run.id)

    with pytest.raises(NotFound):
        await start_run(session, workspace_b.id, "bert", filters={}, sources=["arxiv"], run_id=run.id)


@pytest.mark.asyncio
async def test_start_run_seeds_openalex_cursor_at_one_not_zero(session):
    """OpenAlex's `page` param is 1-based; every other source's cursor is a 0-based offset (I4). Seeding OpenAlex
    at 0 asked its fake for a negative offset and got nothing back "by coincidence," hiding the bug."""
    from app.core.workspace_search import start_run
    workspace = Workspace(name=f"OpenAlex seed {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()

    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv", "openalex"])

    cursors = {
        c.source: c.cursor_json
        for c in (
            await session.execute(select(WorkspaceSearchCursor).where(WorkspaceSearchCursor.run_id == run.id))
        ).scalars()
    }
    assert cursors["openalex"] == {"value": 1}
    assert cursors["arxiv"] == {"value": 0}


@pytest.mark.asyncio
async def test_start_run_orders_sources_by_paper_sources_trust_order(session):
    """D73's merge trust order is app/core/paper_sources.SOURCES; search_batch's `found` dict is insertion-ordered
    and feeds merge()'s ranking directly, so storing sources in whatever order the caller sent them would let the
    caller's field order silently become the trust order instead (bundled minor)."""
    from app.core.workspace_search import start_run
    workspace = Workspace(name=f"Source order {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()

    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv", "openalex", "crossref"])

    assert run.sources_json == ["openalex", "crossref", "arxiv"]  # paper_sources.SOURCES order, not caller order


@pytest.mark.asyncio
async def test_start_run_rejects_non_empty_filters(session):
    """Real per-source filter translation is out of scope for this fix wave; accepting and silently ignoring a
    filter would misreport the search strategy a PRISMA methods section later cites (I6 part 2)."""
    from app.core.errors import InvalidInput
    from app.core.workspace_search import start_run
    workspace = Workspace(name=f"Filters rejected {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()

    with pytest.raises(InvalidInput):
        await start_run(session, workspace.id, "bert", filters={"open_access_only": True}, sources=["arxiv"])


@pytest.mark.asyncio
async def test_stop_run_on_a_non_running_run_is_conflict(session):
    """Stopping only applies to a run actually in flight — same "doesn't apply to the current state" convention
    as start_run's own Conflict on an already-running run (bundled minor)."""
    from app.core.errors import Conflict
    from app.core.workspace_search import start_run, stop_run
    workspace = Workspace(name=f"Stop conflict {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    await session.commit()
    run = await start_run(session, workspace.id, "bert", filters={}, sources=["arxiv"])
    await stop_run(session, run.id)

    with pytest.raises(Conflict):
        await stop_run(session, run.id)


async def test_search_batch_uses_the_per_source_query_override(session, fake_providers, monkeypatch):
    """P11's per-source override (run.query_overrides_json) must actually reach that source's search_page call —
    before this fix it was accepted, stored, and silently ignored (I6 part 1)."""
    import app.core.workspace_search as core_module

    seen_queries = []
    real_page = arxiv.search_page

    async def recording_page(http, query, page_size, cursor):
        seen_queries.append(query)
        return await real_page(http, query, page_size, cursor)

    monkeypatch.setitem(core_module._PAGE_FUNCS, "arxiv", recording_page)

    run = await _new_run(session, ["arxiv"])
    run.query_overrides_json = {"arxiv": "transformer architectures"}
    await session.commit()

    await search_batch(session, fake_providers, run)

    assert seen_queries == ["transformer architectures"]  # not run.query_text ("bert")


async def test_find_or_create_external_ref_prefers_the_doi_match_over_a_weaker_identifier_match(session):
    """Two existing rows: ref_a shares the candidate's DOI; ref_b only shares the candidate's s2_id and has its
    own, unrelated DOI. The OR-match hits both. Before Important 2's ordering fix, `.first()` on the unordered
    result could pick either row arbitrarily — picking ref_b would attach this hit (and later, its import/PDF
    download) to the wrong paper entirely, not just risk a bad backfill. DOI is the strongest identifier, so
    ref_a must win deterministically, and the fix must still not crash or cross-write onto ref_b (this exact
    backfill mechanism corrupted a real row once — the ledger's "Closed Access Fixture" incident)."""
    ref_a = ExternalRef(title="Ref A", doi="10.5555/paperlab-i3-a")
    ref_b = ExternalRef(title="Ref B", doi="10.5555/paperlab-i3-b", s2_id="i3-shared-s2-id")
    session.add_all([ref_a, ref_b])
    await session.commit()

    candidate = Candidate(
        title="New candidate",
        doi="10.5555/paperlab-i3-a",
        s2_id="i3-shared-s2-id",
        pdf_urls=["https://example.test/candidate.pdf"],
    )

    ref = await _find_or_create_external_ref(session, candidate)
    await session.commit()  # must not raise IntegrityError

    assert ref.id == ref_a.id  # the DOI match wins deterministically, not ref_b

    # "i3-shared-s2-id" must still belong to exactly one row — never duplicated onto ref_a.
    holders = (
        await session.execute(select(ExternalRef.id).where(ExternalRef.s2_id == "i3-shared-s2-id"))
    ).scalars().all()
    assert holders == [ref_b.id]

    await session.refresh(ref_a)
    await session.refresh(ref_b)
    assert ref_a.doi == "10.5555/paperlab-i3-a"  # never overwritten by the candidate's own doi
    assert ref_b.doi == "10.5555/paperlab-i3-b"  # untouched — never even loaded as the matched row
    assert ref_a.pdf_urls == candidate.pdf_urls  # ref_a's own DOI matches the candidate's, so this is safe


async def test_insert_hit_is_race_safe_under_a_duplicate_attempt(session):
    """Proxy for two search_batch calls racing on the same (workspace_id, external_ref_id) after a
    stop-then-immediate-restart (enqueue_job has no dedup job id): this suite's per-test session is one
    savepoint-wrapped connection, so two genuinely overlapping transactions aren't reproducible here — two
    sequential calls sharing the same candidate/ref is the accepted proxy (I2 part 2)."""
    workspace = Workspace(name=f"Insert race {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    ref = ExternalRef(title="Racing Paper", doi="10.5555/paperlab-i2-race")
    session.add(ref)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="q", filters_json={}, query_overrides_json={},
        sources_json=["arxiv"], status="running", started_at=datetime.now(timezone.utc), stats_json={},
    )
    session.add(run)
    await session.flush()
    await session.commit()
    candidate = Candidate(title="Racing Paper", doi="10.5555/paperlab-i2-race")

    first = await _insert_hit(session, run, ref, candidate)
    second = await _insert_hit(session, run, ref, candidate)  # the "concurrent" duplicate attempt

    assert (first, second) == (True, False)  # no crash on the duplicate; only the first actually inserted
    count = await session.scalar(
        select(func.count()).select_from(WorkspaceSearchHit).where(WorkspaceSearchHit.external_ref_id == ref.id)
    )
    assert count == 1
