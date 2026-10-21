import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperEvent(Base):
    """One thing that happened to a paper (R21): a free PDF found by the re-check, or a PDF attached. Goes with its
    paper. `seen_at` is set once the owner dismissed the notice."""

    __tablename__ = "paper_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)  # pdf_found | pdf_attached (CHECK in 0053)
    detail: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_paper_events_paper_id", "paper_id"),
        Index("ix_paper_events_kind_seen_at", "kind", "seen_at"),
    )
