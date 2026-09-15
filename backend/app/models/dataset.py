import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    # SET NULL on paper deletion: the owner's captured data outlives the PDF.
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"))
    page: Mapped[int | None]
    region: Mapped[list[float] | None] = mapped_column(JSONB)
    extractor: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    position: Mapped[int]
    name: Mapped[str] = mapped_column(Text, server_default=text("''"))
    unit: Mapped[str | None] = mapped_column(Text)


class DatasetRow(Base):
    __tablename__ = "dataset_rows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    position: Mapped[int]


# Core Tables, like note_anchors: cells are replaced and read in bulk per dataset, never one object at a time.
cell_table = Table(
    "cells",
    Base.metadata,
    Column("row_id", UUID(as_uuid=True), ForeignKey("dataset_rows.id", ondelete="CASCADE"), primary_key=True),
    Column("column_id", UUID(as_uuid=True), ForeignKey("dataset_columns.id", ondelete="CASCADE"), primary_key=True),
    Column("raw", Text, nullable=False, server_default=text("''")),
    Column("value", Float),
    Column("error", Float),
    Column("origin", Text, nullable=False),
    Column("original_raw", Text),
    Column("page", Integer),
    Column("bbox", JSONB),
)


class Chart(Base):
    __tablename__ = "charts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(Text)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


chart_datasets = Table(
    "chart_datasets",
    Base.metadata,
    Column("chart_id", UUID(as_uuid=True), ForeignKey("charts.id", ondelete="CASCADE"), primary_key=True),
    Column("dataset_id", UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True),
)

note_charts = Table(
    "note_charts",
    Base.metadata,
    Column("note_id", UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("chart_id", UUID(as_uuid=True), ForeignKey("charts.id", ondelete="CASCADE"), primary_key=True),
)
