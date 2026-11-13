"""M36 API: the activity list, its clear, and the changes switch over HTTP."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core import mcp_activity
from app.models import McpActivity

pytestmark = pytest.mark.anyio


async def add_row(session, *, tool: str, at: datetime, is_write: bool = False) -> None:
    session.add(
        McpActivity(at=at, tool=tool, arguments='{"x":1}', outcome="ok", duration_ms=7, is_write=is_write)
    )
    await session.flush()


async def test_activity_lists_rows_newest_first_with_the_fields_the_page_shows(client, session):
    now = datetime.now(timezone.utc)
    await add_row(session, tool="get_paper", at=now - timedelta(minutes=5))
    await add_row(session, tool="add_paper", at=now, is_write=True)

    response = await client.get("/api/mcp/activity")

    rows = response.json()
    assert response.status_code == 200
    assert [row["tool"] for row in rows] == ["add_paper", "get_paper"]
    assert set(rows[0]) == {"at", "tool", "arguments", "outcome", "duration_ms", "is_write"}
    assert (rows[0]["arguments"], rows[0]["outcome"], rows[0]["duration_ms"], rows[0]["is_write"]) == (
        '{"x":1}',
        "ok",
        7,
        True,
    )


async def test_activity_limit_defaults_to_100_and_is_checked(client, session):
    now = datetime.now(timezone.utc)
    for index in range(3):
        await add_row(session, tool=f"t{index}", at=now - timedelta(minutes=index))

    assert len((await client.get("/api/mcp/activity?limit=2")).json()) == 2
    assert len((await client.get("/api/mcp/activity")).json()) == 3
    assert (await client.get("/api/mcp/activity?limit=0")).status_code == 422
    assert (await client.get("/api/mcp/activity?limit=501")).status_code == 422


async def test_clear_empties_the_list_and_answers_204(client, session):
    await add_row(session, tool="get_paper", at=datetime.now(timezone.utc))

    response = await client.delete("/api/mcp/activity")

    assert response.status_code == 204
    assert await mcp_activity.recent(session) == []


async def test_settings_default_to_writes_on(client):
    response = await client.get("/api/mcp/settings")

    assert (response.status_code, response.json()) == (200, {"writes_enabled": True})


async def test_put_settings_turns_writes_off_and_back_on(client):
    off = await client.put("/api/mcp/settings", json={"writes_enabled": False})
    assert (off.status_code, off.json()) == (200, {"writes_enabled": False})
    assert (await client.get("/api/mcp/settings")).json() == {"writes_enabled": False}

    on = await client.put("/api/mcp/settings", json={"writes_enabled": True})
    assert (on.status_code, on.json()) == (200, {"writes_enabled": True})


@pytest.mark.parametrize("body", [{}, {"writes_enabled": "maybe"}, {"writes_enabled": True, "extra": 1}])
async def test_put_settings_rejects_bad_bodies(client, body):
    response = await client.put("/api/mcp/settings", json=body)

    assert response.status_code == 422
