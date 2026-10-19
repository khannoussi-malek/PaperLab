import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperMerge(Base):
    """One merge of paper M (merged_id) into paper K (kept_id), or one refused and reported (R16). No FKs: the
    history outlives both papers. `moved` counts the rows per table; `reason` says why a merge was only reported."""

    __tablename__ = "paper_merges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    kept_id: Mapped[uuid.UUID]
    merged_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(Text)  # merged | reported (CHECK in 0052)
    reason: Mapped[str | None] = mapped_column(Text)
    moved: Mapped[dict[str, int]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    identifier: Mapped[str | None] = mapped_column(Text)  # "doi:10.…" or "openalex_id:W…"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
