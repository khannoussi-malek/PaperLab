"""A run must say what each source did: six real runs read "exhausted" while Semantic Scholar failed on all six."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import delete

from app.core import paper_sources, pipeline, prisma_export, queue, search_run_results, workspace_search
from app.models import PaperSources
from app.models.workspace import Workspace
from app.models.workspace_search import WorkspaceSearchCursor, WorkspaceSearchHit, WorkspaceSearchRun

pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

S2_429 = "Client error '429 ' for url 'https://api.semanticscholar.org/graph/v1/paper/search?query=x&offset=0'"
ACM_429 = "Client error '429 Too Many Requests' for url 'https://api.crossref.org/works?mailto=me%40example.org&rows=30'"
RAW = {"arxiv": 100, "acm_dl": 210, "openalex": 28}


def cursor(source, stored, exhausted=False, error=None):
    return WorkspaceSearchCursor(source=source, cursor_json=stored, exhausted=exhausted, last_error=error)


# The cursors the six runs of 2026-11-02 ended with, as read from the database.
ENDED_DURING_COOLDOWN = [
    ("openalex", {"value": 1}, True, None),
    ("semantic_scholar", {"value": 0, "errors": 5, "retry_after": "2026-11-02T14:27:41+00:00"}, False, S2_429),
    ("arxiv", {"value": 100, "errors": 5, "retry_after": "2026-11-02T14:28:58+00:00"}, False, "[Errno -5] No address"),
    ("acm_dl", {"value": 210, "paused": True}, False, None),
]
GAVE_UP = [
    ("openalex", {"value": 1}, True, None),
    ("semantic_scholar", {"value": 0, "errors": 6}, True, S2_429),
    ("arxiv", {"value": 200, "paused": True}, False, None),
    ("acm_dl", {"value": 210, "paused": True}, False, None),
]


def run_of(status="exhausted", stats=None):
    return WorkspaceSearchRun(status=status, stats_json=stats or {"per_source_raw_count": RAW})


def report(rows, status="exhausted"):
    run = run_of(status)
    return run, search_run_results.source_results(run, [cursor(*row) for row in rows])


@pytest.mark.parametrize("rows", [ENDED_DURING_COOLDOWN, GAVE_UP])
def test_the_runs_that_read_exhausted_report_partial_with_a_reason_per_source(rows):
    run, results = report(rows)
    assert search_run_results.outcome(run.status, results) == "partial"
    assert "semantic_scholar" in search_run_results.failed_sources(run, results)
    by_source = {r.source: r for r in results}
    assert "HTTP 429 from api.semanticscholar.org" in by_source["semantic_scholar"].reason
    assert by_source["openalex"].state == "complete" and by_source["openalex"].reason is None
    assert by_source["acm_dl"].state == "paused" and "200 results" in by_source["acm_dl"].reason


def test_states_read_from_the_cursor():
    _, ended = report(ENDED_DURING_COOLDOWN)
    assert {r.source: r.state for r in ended}["semantic_scholar"] == "cooling_down"
    _, gave_up = report(GAVE_UP)
    assert {r.source: r.state for r in gave_up}["semantic_scholar"] == "gave_up"
    _, off = report([("arxiv", {"value": 0, "disabled": True}, True, None)])
    assert off[0].state == "disabled"
    _, running = report([("arxiv", {"value": 20}, False, None)], status="running")
    assert running[0].state == "fetching"
    _, stopped = report([("arxiv", {"value": 20}, False, None)], status="stopped")
    assert stopped[0].state == "paused"


def test_every_source_running_dry_is_complete_and_a_running_run_is_running():
    run, results = report([("openalex", {"value": 1}, True, None), ("arxiv", {"value": 20}, True, None)])
    assert search_run_results.outcome(run.status, results) == "complete"
    assert search_run_results.outcome("running", results) == "running"


def test_a_short_error_leaves_out_the_url_and_the_contact_email_in_it():
    assert search_run_results.short_error(ACM_429) == "HTTP 429 from api.crossref.org"
    assert search_run_results.short_error("[Errno -5] No address") == "[Errno -5] No address"
    assert search_run_results.short_error(None) is None
    assert "sk-test" not in search_run_results.short_error("Redirect to https://x.org/?api_key=sk-test-1234567890abcdef")


def test_a_source_that_failed_with_nothing_is_not_searched_but_one_that_returned_results_is():
    _, results = report(ENDED_DURING_COOLDOWN)
    reached, missed = search_run_results.searched(results)
    assert missed == ["semantic_scholar"]
    assert "arxiv" in reached  # failing at the end, but it returned 100


def test_a_source_the_run_stopped_before_asking_is_not_searched():
    run = run_of("stopped", {"per_source_raw_count": {}})
    results = search_run_results.source_results(run, [cursor("arxiv", {"value": 0})])
    assert results[0].state == "paused" and search_run_results.searched(results) == ([], ["arxiv"])


def test_a_source_that_ran_dry_with_nothing_was_searched():
    run = run_of("exhausted", {"per_source_raw_count": {}})
    results = search_run_results.source_results(run, [cursor("arxiv", {"value": 0}, True)])
    assert search_run_results.searched(results) == (["arxiv"], [])


@pytest.fixture
async def stored_run(session):
    await session.execute(delete(PaperSources))
    workspace = Workspace(name=f"Results {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    run = WorkspaceSearchRun(
        workspace_id=workspace.id, query_text="creativity", filters_json={}, query_overrides_json={},
        sources_json=["openalex", "semantic_scholar", "arxiv", "acm_dl"], status="exhausted",
        started_at=datetime.now(timezone.utc),
        stats_json={"per_source_raw_count": RAW, "failed_sources": [], "per_source_new_hits": {"arxiv": 7}},
    )
    session.add(run)
    await session.flush()
    for source, stored, exhausted, error in ENDED_DURING_COOLDOWN:
        session.add(WorkspaceSearchCursor(
            run_id=run.id, source=source, cursor_json=stored, exhausted=exhausted, last_error=error,
        ))
    await session.flush()
    return run


def hit(run, number, **fields):
    return WorkspaceSearchHit(
        workspace_id=run.workspace_id, run_id=run.id, source_method="database_search",
        normalized_title=f"paper {number}", first_seen_at=datetime.now(timezone.utc), **fields,
    )


async def test_a_suggestion_from_before_flags_existed_counts_as_judged(session, stored_run):
    session.add(hit(stored_run, 9, suggestion="include", suggestion_model="m", suggestion_flags=None))
    await session.flush()
    counts = (await search_run_results.prescreen_counts(session, [stored_run.id]))[stored_run.id]
    assert (counts.judged, counts.not_judged) == (1, 0)


async def test_both_tools_return_the_same_report(session, stored_run):
    session.add_all([
        hit(stored_run, 1, suggestion="include", suggestion_model="m", suggestion_flags=[]),
        hit(stored_run, 2, suggestion="unsure", suggestion_flags=["no_abstract"]),
        hit(stored_run, 3, suggestion="unsure", suggestion_model="m", suggestion_flags=["model_error"]),
        hit(stored_run, 4),
    ])
    await session.flush()
    workspace = await session.get(Workspace, stored_run.workspace_id)

    one = await pipeline.get_search_run(session, stored_run.id)
    [listed] = await pipeline.list_search_runs(session, workspace.name)

    fields = ("hit_count", "per_source_raw_count", "failed_sources", "source_results", "outcome", "prescreen")
    assert {f: getattr(one, f) for f in fields} == {f: getattr(listed, f) for f in fields}
    assert one.hit_count == 4 and one.per_source_raw_count == RAW and one.outcome == "partial"
    assert one.failed_sources == ["arxiv", "semantic_scholar"]  # stats_json's own list is empty, as on four real runs
    assert [r.new_hits for r in one.source_results if r.source == "arxiv"] == [7]
    assert (one.prescreen.judged, one.prescreen.not_judged, one.prescreen.not_asked) == (1, 2, 1)


async def test_prisma_does_not_count_a_source_that_failed_with_nothing_as_searched(session, stored_run):
    per_run = await prisma_export.prisma_export(session, stored_run.workspace_id, stored_run.id)
    assert "semantic_scholar" in per_run.sources_not_searched
    assert "semantic_scholar" not in per_run.sources_searched and "arxiv" in per_run.sources_searched
    assert any("Semantic Scholar" in note and "did not answer" in note for note in per_run.notes)

    combined = await prisma_export.prisma_export(session, stored_run.workspace_id, None)
    assert combined.sources_not_searched == ["semantic_scholar"]
    assert combined.runs[0]["sources_not_searched"] == ["semantic_scholar"]


async def test_starting_a_run_warns_before_the_wait_about_a_source_that_will_give_nothing(session, monkeypatch):
    from conftest import FakeArq

    monkeypatch.setattr(queue, "_pool", FakeArq())
    await session.execute(delete(PaperSources))
    workspace = Workspace(name=f"Warn {uuid.uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    sources = ["semantic_scholar", "arxiv", "openalex"]
    out = await pipeline.start_search_run(session, workspace.name, "creativity", sources)
    # Defaults: Semantic Scholar on with no key, arXiv fine, OpenAlex off.
    assert [w.source for w in out.warnings] == ["openalex", "semantic_scholar"]
    assert "API key" in [w.message for w in out.warnings if w.source == "semantic_scholar"][0]
    assert (await pipeline.get_search_run(session, out.id)).warnings == out.warnings  # still there while it runs


async def test_a_key_clears_the_warning_and_settings_shows_the_same_notice(session):
    sources = paper_sources.SourceSettings()
    notice = {s.id: s.notice for s in paper_sources.view(sources).sources}
    assert "API key" in notice["semantic_scholar"]
    assert notice["arxiv"] is None and notice["openalex"] is None  # OpenAlex is off, not failing
    assert paper_sources.search_warnings(sources, ["semantic_scholar"])[0]["message"] == notice["semantic_scholar"]

    keyed = replace(sources, api_keys={**sources.api_keys, "semantic_scholar": "s2-test-key"})
    assert {s.id: s.notice for s in paper_sources.view(keyed).sources}["semantic_scholar"] is None
    assert paper_sources.search_warnings(keyed, ["semantic_scholar"]) == []


async def test_workspace_search_counts_new_hits_for_every_source_that_found_them(session, stored_run):
    from app.core.candidates import Candidate

    found = {"arxiv": [Candidate(title="Shared paper", doi="10.1/shared", sources=("arxiv", "openalex"))]}
    counted = workspace_search.Counter()
    added = await workspace_search._store_candidates_as_hits(
        session, stored_run, "database_search", found, new_by_source=counted
    )
    assert added == 1 and counted["arxiv"] == 1


def test_short_error_reads_httpxs_real_message():
    request = httpx.Request("GET", "https://api.crossref.org/works?mailto=me%40example.org")
    with pytest.raises(httpx.HTTPStatusError) as raised:
        httpx.Response(429, request=request).raise_for_status()
    assert search_run_results.short_error(str(raised.value)) == "HTTP 429 from api.crossref.org"
