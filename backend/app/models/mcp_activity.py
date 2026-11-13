import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class McpActivity(Base):
    """One row per tool call an MCP client made on the library (M36). Capped at 1000 rows by app.core.mcp_activity."""

    __tablename__ = "mcp_activity"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    tool: Mapped[str] = mapped_column(Text)
    arguments: Mapped[str] = mapped_column(Text)  # a summary, never the full arguments
    outcome: Mapped[str] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)
    is_write: Mapped[bool] = mapped_column(Boolean)


class McpSettings(Base):
    """The one row (id true) with the owner's switch for changes from Claude."""

    __tablename__ = "mcp_settings"

    id: Mapped[bool] = mapped_column(primary_key=True, server_default=text("true"))
    writes_enabled: Mapped[bool] = mapped_column(server_default=text("true"))
