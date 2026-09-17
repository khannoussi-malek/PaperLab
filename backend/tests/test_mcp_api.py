"""The Connect Claude page's two routes: the PaperLab folder Compose passed in, and the server check."""

import pytest

from app.config import settings
from app.core import mcp_check

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(("paperlab_dir", "folder"), [("/Users/me/PaperLab", "/Users/me/PaperLab"), ("", None)])
async def test_setup_gives_the_folder_compose_was_started_in_or_null(client, monkeypatch, paperlab_dir, folder):
    monkeypatch.setattr(settings, "paperlab_dir", paperlab_dir)

    response = await client.get("/api/mcp/setup")

    assert (response.status_code, response.json()) == (200, {"folder": folder})


async def test_check_returns_what_the_server_check_found(client, monkeypatch):
    async def missing_tools(*, timeout: float = 30) -> mcp_check.McpCheck:
        return mcp_check.McpCheck(ok=False, tools=["get_paper"], detail="The MCP server is missing tools: create_note.")

    monkeypatch.setattr(mcp_check, "check_server", missing_tools)

    response = await client.post("/api/mcp/check")

    assert (response.status_code, response.json()) == (
        200,
        {"ok": False, "tools": ["get_paper"], "detail": "The MCP server is missing tools: create_note."},
    )
