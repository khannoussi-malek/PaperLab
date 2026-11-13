"""M36: every tool call an MCP client makes is listed in the app, and the owner can turn off the changes (writes)."""

import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from mcp import Client
from mcp_fixtures import *  # noqa: F403
from mcp_fixtures import call, result
from sqlalchemy import delete, func, select

from app.core import mcp_activity, workspaces
from app.models import McpActivity, Paper
from mcp_server import server

pytestmark = pytest.mark.anyio
RUN = uuid.uuid4().hex[:8]
PDF = b"%PDF-1.7\n%an uploaded paper\n"


@pytest.fixture(autouse=True)
async def empty_log(session):
    """Tests that run a real MCP server process (test_mcp_stdio, test_mcp_check) commit log rows to the test database;
    start each test from an empty log, inside its own rolled-back transaction."""
    await session.execute(delete(McpActivity))


async def log_rows(session) -> list[mcp_activity.ActivityRow]:
    return await mcp_activity.recent(session, limit=2 * mcp_activity.ACTIVITY_CAP)


async def switch(session, on: bool) -> None:
    await mcp_activity.set_writes_enabled(session, on)


# The summary: short arguments as compact JSON, long strings cut, base64 uploads replaced, the whole capped.


async def test_short_arguments_are_kept_as_compact_json():
    assert mcp_activity.summarise({"workspace": "W", "limit": 5}) == '{"workspace":"W","limit":5}'


async def test_a_long_string_is_cut_to_200_and_an_ellipsis():
    summary = mcp_activity.summarise({"claim": "a" * 2000})
    assert summary == '{"claim":"' + "a" * 200 + '…"}'


async def test_a_base64_upload_is_replaced_by_its_decoded_size():
    summary = mcp_activity.summarise({"workspace": "W", "filename": "x.pdf", "pdf_base64": "A" * 40000})
    assert '"pdf_base64":"<30000 bytes>"' in summary
    assert len(summary) < 200


async def test_the_whole_summary_is_capped_at_500_characters():
    summary = mcp_activity.summarise({"items": ["x" * 150] * 10})
    assert len(summary) == 500 and summary.endswith("…")


# The log: one row per call, the cap, the switch, clearing.


async def test_record_writes_one_row_with_its_fields(session):
    await mcp_activity.record(
        session, tool="add_paper", arguments={"identifier": "10.1/x"}, outcome="ok", duration_ms=12, is_write=True
    )

    [row] = await log_rows(session)
    assert (row.tool, row.arguments, row.outcome, row.duration_ms, row.is_write) == (
        "add_paper",
        '{"identifier":"10.1/x"}',
        "ok",
        12,
        True,
    )
    assert row.at.tzinfo is not None


async def test_the_1001st_call_deletes_exactly_the_oldest_row(session):
    base = datetime.now(timezone.utc) - timedelta(days=1)
    session.add_all(
        McpActivity(
            at=base + timedelta(seconds=i),
            tool=f"tool_{i}",
            arguments="{}",
            outcome="ok",
            duration_ms=1,
            is_write=False,
        )
        for i in range(mcp_activity.ACTIVITY_CAP)
    )
    await session.flush()

    await mcp_activity.record(session, tool="newest", arguments={}, outcome="ok", duration_ms=1, is_write=False)

    tools = [row.tool for row in await log_rows(session)]
    assert len(tools) == mcp_activity.ACTIVITY_CAP
    assert "tool_0" not in tools and "tool_1" in tools and tools[0] == "newest"


async def test_clear_empties_the_log_and_counts_what_it_removed(session):
    for tool in ("a", "b", "c"):
        await mcp_activity.record(session, tool=tool, arguments={}, outcome="ok", duration_ms=1, is_write=False)

    assert await mcp_activity.clear(session) == 3
    assert await log_rows(session) == []


async def test_writes_are_on_by_default_and_the_switch_round_trips(session):
    assert await mcp_activity.writes_enabled(session) is True

    assert await mcp_activity.set_writes_enabled(session, False) is False
    assert await mcp_activity.writes_enabled(session) is False

    await mcp_activity.set_writes_enabled(session, True)
    assert await mcp_activity.writes_enabled(session) is True


# Through the MCP server: the hook around every tool call.


async def test_a_read_call_is_listed_as_ok_and_not_a_change(session):
    result(await call("list_workspaces"))

    [row] = await log_rows(session)
    assert (row.tool, row.outcome, row.is_write) == ("list_workspaces", "ok", False)


async def test_a_recoverable_error_is_the_outcome(session):
    response = await call("list_tags", workspace="x" * 2000)

    assert response.is_error
    [row] = await log_rows(session)
    assert row.outcome == response.structured_content["error"] and row.is_write is False
    assert len(row.arguments) <= 500


async def test_a_write_is_refused_when_off_and_does_not_run(session, jobs, pdf_dir):
    ws = f"Off {RUN}"
    await workspaces.create(session, ws)
    await switch(session, False)
    before = await session.scalar(select(func.count()).select_from(Paper))

    response = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=base64.b64encode(PDF).decode())

    assert response.is_error
    assert response.structured_content == {
        "error": "writes_disabled",
        "detail": "The owner has turned off changes from Claude in PaperLab's Connect Claude page.",
    }
    assert jobs.jobs == [] and list(pdf_dir.glob("*")) == []
    assert await session.scalar(select(func.count()).select_from(Paper)) == before
    [row] = await log_rows(session)
    assert (row.tool, row.outcome, row.is_write) == ("upload_paper", "writes_disabled", True)


async def test_a_write_runs_and_is_listed_as_a_change_when_on(session, jobs, pdf_dir):
    ws = f"On {RUN}"
    await workspaces.create(session, ws)

    response = await call("upload_paper", workspace=ws, filename="x.pdf", pdf_base64=base64.b64encode(PDF).decode())

    assert not response.is_error and len(jobs.jobs) == 1
    [row] = await log_rows(session)
    assert (row.tool, row.outcome, row.is_write) == ("upload_paper", "ok", True)


async def test_reads_keep_working_with_writes_off(session):
    await switch(session, False)

    result(await call("list_workspaces"))

    [row] = await log_rows(session)
    assert (row.outcome, row.is_write) == ("ok", False)


async def test_a_prompt_listing_is_not_logged_as_a_tool_call(session):
    async with Client(server.mcp) as client:
        await client.list_prompts()

    assert await log_rows(session) == []


async def test_a_tool_that_raises_is_logged_as_failed_and_its_error_reaches_the_client(session, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(workspaces, "list_workspaces", boom)

    response = await call("list_workspaces")

    assert response.is_error and "Error executing tool list_workspaces" in response.content[0].text
    [row] = await log_rows(session)
    assert (row.tool, row.outcome, row.is_write) == ("list_workspaces", "failed", False)


async def test_a_logging_failure_never_breaks_the_call(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("log table gone")

    monkeypatch.setattr(mcp_activity, "record", broken)

    response = await call("list_workspaces")

    assert not response.is_error
