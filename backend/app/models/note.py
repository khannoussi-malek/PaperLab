import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, ForeignKey, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Provenance(StrEnum):
    HUMAN = "human"
    LLM = "llm"
    LLM_EDITED = "llm_edited"


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    body: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text)
    color: Mapped[str] = mapped_column(Text, server_default=text("'#facc15'"))
    # The database enforces the FK to llm_outputs (ON DELETE SET NULL since 0003).
    source_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


# A Core Table, not a mapped class: the primary key includes the jsonb bbox, and the ORM
# identity map can't hash a list. Anchors are only inserted and read in bulk anyway.
note_anchors = Table(
    "note_anchors",
    Base.metadata,
    Column("note_id", UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("paper_id", UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("chunk_id", UUID(as_uuid=True)),
    Column("page", Integer, primary_key=True),
    Column("bbox", JSONB, primary_key=True),
    Column("quoted_text", Text),
)
