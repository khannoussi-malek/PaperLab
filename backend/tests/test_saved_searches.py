"""Saved searches CRUD (M39 F2)."""

import uuid
from datetime import datetime, timezone

import pytest

from app.core import saved_searches, workspaces
from app.core.errors import DomainError, InvalidInput, NotFound

pytestmark = pytest.mark.anyio

UTC = timezone.utc
RUN = uuid.uuid4().hex[:8]


async def test_create_computes_the_next_run_and_lists_it(session):
    ws = await workspaces.create(session, f"Saved {RUN}")
    now = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    view = await saved_searches.create(session, ws.id, query="llm creativity", schedule="0 2 * * 1",
                                       timezone="UTC", sources=["arxiv"], year_from=2023, year_to=2026, now=now)
    assert view.next_run_at == datetime(2026, 10, 19, 2, 0, tzinfo=UTC)
    assert (view.schedule_kind, view.time, view.weekday) == ("weekly", "02:00", 1)
    assert [v.id for v in await saved_searches.list_for_workspace(session, ws.id)] == [view.id]


async def test_disabling_clears_next_run_and_enabling_recomputes_it_from_now(session):
    ws = await workspaces.create(session, f"Toggle {RUN}")
    t0 = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    view = await saved_searches.create(session, ws.id, query="q", schedule="0 2 * * *", timezone="UTC", now=t0)
    off = await saved_searches.update(session, ws.id, view.id, {"enabled": False}, now=t0)
    on = await saved_searches.update(session, ws.id, view.id, {"enabled": True},
                                     now=datetime(2026, 10, 20, 9, 0, tzinfo=UTC))
    assert off.next_run_at is None
    assert on.next_run_at == datetime(2026, 10, 21, 2, 0, tzinfo=UTC)


@pytest.mark.parametrize("bad, code", [
    ({"query": "  "}, "invalid_input"), ({"sources": ["google_scholar"]}, "unknown_source"),
    ({"year_from": 2026, "year_to": 2020}, "invalid_years"), ({"schedule": "nope"}, "invalid_schedule"),
    ({"timezone": "Nowhere/City"}, "invalid_timezone"),
])
async def test_bad_fields_are_refused(session, bad, code):
    ws = await workspaces.create(session, f"Bad {code} {RUN}")
    fields = {"query": "q", "schedule": "0 2 * * *", "timezone": "UTC", **bad}
    with pytest.raises(DomainError) as raised:
        await saved_searches.create(session, ws.id, **fields)
    assert str(raised.value) == code or (code == "invalid_input" and isinstance(raised.value, InvalidInput))


async def test_another_workspaces_saved_search_is_not_found(session):
    mine = await workspaces.create(session, f"Mine {RUN}")
    theirs = await workspaces.create(session, f"Theirs {RUN}")
    view = await saved_searches.create(session, theirs.id, query="q", schedule="0 2 * * *", timezone="UTC")
    with pytest.raises(NotFound):
        await saved_searches.update(session, mine.id, view.id, {"enabled": False})
    with pytest.raises(NotFound):
        await saved_searches.delete(session, mine.id, view.id)


async def test_a_refused_update_of_a_disabled_search_changes_nothing(session):
    ws = await workspaces.create(session, f"Disabled {RUN}")
    view = await saved_searches.create(session, ws.id, query="q", schedule="0 2 * * *", timezone="UTC")
    await saved_searches.update(session, ws.id, view.id, {"enabled": False})
    with pytest.raises(InvalidInput) as raised:
        await saved_searches.update(session, ws.id, view.id, {"enabled": False, "timezone": "Nowhere/City"})
    assert str(raised.value) == "invalid_timezone"
    assert (await saved_searches.get(session, view.id)).timezone == "UTC"


# --- The inbox (M7.6 on saved searches): what a saved search found since the reader last looked ---------------------

async def _found(session, ws, saved_id, at, *, status=None, title="t"):
    """One hit first seen at `at` by a run of saved search `saved_id` (None: a run the reader started by hand)."""
    from app.models.references import ExternalRef
    from app.models.workspace_search import WorkspaceSearchHit, WorkspaceSearchRun

    run = WorkspaceSearchRun(workspace_id=ws.id, query_text="q", filters_json={}, query_overrides_json={},
                             sources_json=["arxiv"], status="exhausted", started_at=at, saved_search_id=saved_id)
    ref = ExternalRef(title=title, year=2026)
    session.add_all([run, ref])
    await session.flush()
    hit = WorkspaceSearchHit(workspace_id=ws.id, run_id=run.id, external_ref_id=ref.id, source_method="database_search",
                             normalized_title=f"{title} {uuid.uuid4().hex}", first_seen_at=at, stage1_status=status)
    session.add(hit)
    await session.commit()
    return hit


async def test_new_hits_counts_unscreened_hits_this_search_found_since_the_last_look(session):
    ws = await workspaces.create(session, f"Inbox {RUN}")
    t0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    view = await saved_searches.create(session, ws.id, query="q", schedule="0 2 * * *", timezone="UTC", now=t0)
    assert view.seen_at == t0 and view.new_hits == 0
    later = datetime(2026, 11, 2, 2, 0, tzinfo=UTC)
    await _found(session, ws, view.id, datetime(2026, 10, 31, tzinfo=UTC))  # before the last look
    await _found(session, ws, view.id, later)  # new
    await _found(session, ws, view.id, later, status="not_relevant")  # already screened
    await _found(session, ws, None, later)  # a search the reader ran by hand
    assert (await saved_searches.get(session, view.id)).new_hits == 1


async def test_marking_seen_moves_the_last_look_and_clears_the_count(session):
    ws = await workspaces.create(session, f"Seen {RUN}")
    t0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    view = await saved_searches.create(session, ws.id, query="q", schedule="0 2 * * *", timezone="UTC", now=t0)
    await _found(session, ws, view.id, datetime(2026, 11, 2, tzinfo=UTC))
    t1 = datetime(2026, 11, 3, tzinfo=UTC)
    seen = await saved_searches.mark_seen(session, ws.id, view.id, now=t1)
    assert (seen.seen_at, seen.new_hits) == (t1, 0)
    with pytest.raises(NotFound):
        await saved_searches.mark_seen(session, (await workspaces.create(session, f"Other {RUN}")).id, view.id)


async def test_the_hit_list_narrows_to_one_saved_searchs_finds_after_a_time(session):
    from app.core import workspace_search

    ws = await workspaces.create(session, f"Narrow {RUN}")
    t0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    view = await saved_searches.create(session, ws.id, query="q", schedule="0 2 * * *", timezone="UTC", now=t0)
    await _found(session, ws, view.id, datetime(2026, 10, 30, tzinfo=UTC), title="old")
    new = await _found(session, ws, view.id, datetime(2026, 11, 2, tzinfo=UTC), title="new")
    await _found(session, ws, None, datetime(2026, 11, 2, tzinfo=UTC), title="by hand")
    items, _ = await workspace_search.list_hits(session, ws.id, saved_search_id=view.id, found_after=t0)
    assert [i["id"] for i in items] == [new.id]
