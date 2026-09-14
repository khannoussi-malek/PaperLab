import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import REAL, Boolean, Column, DateTime, ForeignKey, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Author(Base):
    """A person as OpenAlex identifies them. Never created from a name alone (addendum §6a)."""

    __tablename__ = "authors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    openalex_id: Mapped[str | None] = mapped_column(Text, unique=True)
    orcid: Mapped[str | None] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    alt_names: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    last_institution: Mapped[str | None] = mapped_column(Text)
    works_count: Mapped[int | None]
    cited_by_count: Mapped[int | None]
    h_index: Mapped[int | None]
    topics: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Core Tables, like note_anchors: they are only replaced and read in bulk.
paper_authors = Table(
    "paper_authors",
    Base.metadata,
    Column("paper_id", UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", UUID(as_uuid=True), ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False),  # 1 = first author
    Column("is_corresponding", Boolean, server_default=text("false")),
    Column("institution", Text),  # the affiliation printed on this paper, not today's
)

# External facts about a paper. The user's own structure (workspaces) lives elsewhere and never merges in.
paper_topics = Table(
    "paper_topics",
    Base.metadata,
    Column("paper_id", UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("source", Text, primary_key=True),  # 'author' | 'openalex' | 'venue'
    Column("label", Text, primary_key=True),
    Column("score", REAL),  # NULL for author keywords
)
