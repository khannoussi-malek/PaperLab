"""PaperLab over MCP, on stdio (M6). Claude Desktop starts it inside the api container (D89):

    docker compose -f <repo>/docker-compose.yml exec -T api python -m mcp_server

Each tool opens a session, calls one core service and returns its dataclasses. There is no SQL and no logic here: a
DomainError becomes a result the client's model can read and retry with (D93). Stdout is the protocol pipe, so
nothing in this process may print.
"""

import functools
import json
import re
import uuid

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from app.core import graph, library, notes
from app.core.errors import Conflict, DomainError, InvalidInput, NotFound
from app.db import SessionLocal

# ponytail: the embedding model loads on the first search (seconds). Warm it up in a lifespan if a first search
# times out in Claude Desktop.
mcp = MCPServer(
    "paperlab",
    instructions=(
        "PaperLab is the owner's research library. Search it with search_library, read a paper's outline and notes "
        "with get_paper, walk to connected papers with related_papers, and save a note on a passage with create_note."
    ),
)
sessions = SessionLocal  # tests point this at their rolled-back session
READ_ONLY = ToolAnnotations(read_only_hint=True)
_CODE = re.compile(r"[a-z]+(?:_[a-z]+)+")
_KINDS = {NotFound: "not_found", InvalidInput: "invalid_input", Conflict: "conflict"}


def recoverable(tool):
    """Turns a DomainError into an is_error result: {"error": code, **details}. The code is the error's message when
    that is one (e.g. unknown_workspace), else its kind, with the message as "detail"."""

    @functools.wraps(tool)
    async def call(*args, **kwargs):
        try:
            return await tool(*args, **kwargs)
        except DomainError as exc:
            message = str(exc)
            if _CODE.fullmatch(message):
                error = {"error": message, **exc.details}
            else:
                error = {"error": _KINDS.get(type(exc), "invalid_input"), "detail": message, **exc.details}
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(error))], structured_content=error, is_error=True
            )

    return call


@mcp.tool(annotations=READ_ONLY)
@recoverable
async def search_library(query: str, workspace: str | None = None) -> list[library.Passage]:
    """Passages from the owner's papers closest to `query`, closest first (at most 3 from one paper). Leave out
    `workspace` to search the whole library, or give a workspace's exact name; an unknown name answers with the
    names that exist."""
    async with sessions() as session:
        return await library.search(session, query, workspace)


@mcp.tool(annotations=READ_ONLY)
@recoverable
async def get_paper(paper_id: uuid.UUID) -> library.PaperCard:
    """A paper's details, its section outline with start pages, its workspaces, and every note on it. Each note has a
    provenance: `human` is the owner's own writing; `llm` and `llm_edited` were written by an AI."""
    async with sessions() as session:
        return await library.paper_card(session, paper_id)


@mcp.tool(annotations=READ_ONLY)
@recoverable
async def related_papers(paper_id: uuid.UUID, hops: int = 1) -> list[graph.Related]:
    """Library papers connected to this one within `hops` links (1 to 3), nearest first. `via` says how: same_workspace,
    co_anchored (a note on both), co_authored, shares_topic, cites (this paper cites it) or cited_by (it cites this
    paper)."""
    async with sessions() as session:
        return await graph.related(session, paper_id, hops)


@mcp.tool()
@recoverable
async def create_note(body: str, paper_id: uuid.UUID, quoted_text: str) -> notes.NoteView:
    """Save a note on a paper, anchored on `quoted_text`. Copy quoted_text exactly from one passage search_library
    returned for this paper, long enough to occur only once. The note is shown to the owner as written by AI."""
    async with sessions() as session:
        return await notes.create_llm_note(session, paper_id, body, quoted_text)
