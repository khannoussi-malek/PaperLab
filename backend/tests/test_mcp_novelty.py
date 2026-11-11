"""The novelty_check MCP tool through an in-process client, against the real database in the test transaction (P12)."""

import uuid
from contextlib import asynccontextmanager

import pytest
from pdf_papers import chunked_paper
from test_mcp_server import call

from app.core import workspaces
from app.providers import embedding
from mcp_server import server

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database (D37)


@pytest.fixture(autouse=True)
def tools_use_the_test_session(session, embedder, monkeypatch):
    """Each tool opens `server.sessions()`: give it this test's rolled-back session, and a fake query embedder."""

    @asynccontextmanager
    async def test_session():
        yield session

    monkeypatch.setattr(server, "sessions", test_session)
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)


async def test_novelty_check_answers_the_report(session, tmp_path, embedder):
    paper, _, vectors = await chunked_paper(session, tmp_path, title="Close paper")
    workspace = await workspaces.create(session, f"MCP novelty {RUN}")
    await workspaces.add_paper(session, workspace.id, paper.id)
    embedder.vectors["search_query: my idea"] = vectors[0]
    result = await call("novelty_check", text="my idea", workspace=f"MCP novelty {RUN}")
    assert not result.is_error, result.content
    report = result.structured_content
    assert report["papers"][0]["title"] == "Close paper" and report["papers"][0]["label"] == "very close"
    assert "only covers your own library" in report["note"]


async def test_novelty_check_refuses_text_over_the_limit():
    result = await call("novelty_check", text="x" * 6001)
    assert result.is_error and result.structured_content["error"] == "text_too_long"


async def test_novelty_check_without_a_search_model_is_a_recoverable_error(monkeypatch):
    monkeypatch.setattr(embedding, "get_model", lambda: None)
    result = await call("novelty_check", text="my idea")
    assert result.is_error and result.structured_content["error"] == "search_not_set_up"
