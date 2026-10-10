from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HarvestCursor(Base):
    """One row per periodic-harvest source (M32 batch 6), tracking its own last-synced point so a
    restarted job resumes instead of re-harvesting from scratch. Not scoped to a run, unlike
    WorkspaceSearchCursor -- a harvest source has exactly one ongoing sync, independent of any user
    action."""

    __tablename__ = "harvest_cursors"

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
