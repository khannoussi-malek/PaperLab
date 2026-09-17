from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.core import mcp_check

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpSetupOut(BaseModel):
    # The folder `docker compose up` ran in (PAPERLAB_DIR), or null when the API runs outside Compose.
    folder: str | None


class McpCheckOut(BaseModel):
    ok: bool
    tools: list[str]
    detail: str | None


@router.get("/setup")
async def mcp_setup() -> McpSetupOut:
    return McpSetupOut(folder=settings.paperlab_dir or None)


@router.post("/check")
async def check_mcp_server() -> McpCheckOut:
    """Starts the MCP server as a client would and reads the library through it. Up to 30 seconds."""
    return await mcp_check.check_server()
