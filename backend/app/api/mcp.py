from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.config import settings
from app.core import mcp_activity, mcp_check
from app.schemas.mcp_activity import ActivityOut, WritesSettingIn, WritesSettingOut

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


@router.get("/activity")
async def list_activity(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[ActivityOut]:
    """The tool calls MCP clients made on the library, newest first."""
    return [ActivityOut.model_validate(row) for row in await mcp_activity.recent(session, limit)]


@router.delete("/activity", status_code=204)
async def clear_activity(session: SessionDep) -> Response:
    await mcp_activity.clear(session)
    return Response(status_code=204)


@router.get("/settings")
async def get_settings(session: SessionDep) -> WritesSettingOut:
    return WritesSettingOut(writes_enabled=await mcp_activity.writes_enabled(session))


@router.put("/settings")
async def put_settings(payload: WritesSettingIn, session: SessionDep) -> WritesSettingOut:
    return WritesSettingOut(writes_enabled=await mcp_activity.set_writes_enabled(session, payload.writes_enabled))
