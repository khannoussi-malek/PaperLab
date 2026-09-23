import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExternalRef(Base):
    """A paper some library paper cites or is cited by. Not a paper: no chunks, no status (addendum §3b)."""

    __tablename__ = "external_refs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    s2_id: Mapped[str | None] = mapped_column(Text, unique=True)
    openalex_id: Mapped[str | None] = mapped_column(Text, unique=True)
    doi: Mapped[str | None] = mapped_column(Text)
    arxiv_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'"))
    year: Mapped[int | None]
    venue: Mapped[str | None] = mapped_column(Text)
    cited_by_count: Mapped[int | None]
    pdf_urls: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'"))
    title_embedding: Mapped[Any | None] = mapped_column(Vector(768))
    title_embed_model: Mapped[str | None] = mapped_column(Text)
    # Set once on import: every paper citing this reference then shows it in the library.
    imported_as: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    core_id: Mapped[str | None] = mapped_column(Text, default=None)


paper_references = Table(
    "paper_references",
    Base.metadata,
    Column("paper_id", UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("ref_id", UUID(as_uuid=True), ForeignKey("external_refs.id", ondelete="CASCADE"), primary_key=True),
    Column("direction", Text, primary_key=True),
    Column("position", Integer, nullable=False),
)


class NoteEmbedding(Base):
    """A note's vector for ranking references by closeness to what the reader writes about (D81)."""

    __tablename__ = "note_embeddings"

    note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[Any] = mapped_column(Vector(768))
    embed_model: Mapped[str] = mapped_column(Text)
    noted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
