import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Schema lives in alembic/versions; these mappings cover the columns the app reads/writes.
# chunks.tsv is a generated column and deliberately unmapped.


class PaperStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    ENRICHING = "enriching"
    READY = "ready"
    FAILED = "failed"


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    doi: Mapped[str | None] = mapped_column(Text, unique=True)
    openalex_id: Mapped[str | None] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    year: Mapped[int | None]
    venue: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int | None]
    status: Mapped[str] = mapped_column(Text, server_default=PaperStatus.UPLOADED)
    status_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    page: Mapped[int]
    bbox: Mapped[list[list[float]]] = mapped_column(JSONB)
    section_title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any | None] = mapped_column(Vector(768))
    embed_model: Mapped[str] = mapped_column(Text)
    strategy_ver: Mapped[int]
