import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

NOW = text("now()")


class Manuscript(Base):
    __tablename__ = "manuscripts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text)
    main_file: Mapped[str] = mapped_column(Text, server_default="main.tex")
    checklist: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    compile_status: Mapped[str] = mapped_column(Text, server_default="never")  # never | running | ok | failed
    compile_requested: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    compile_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compile_log: Mapped[str | None] = mapped_column(Text)
    compile_friendly: Mapped[str | None] = mapped_column(Text)  # package_missing | biber_unsupported | ...
    compile_errors: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptFile(Base):
    __tablename__ = "manuscript_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)  # exactly one of text / data is set
    data: Mapped[bytes | None] = mapped_column(LargeBinary)
    size: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptCiteKey(Base):
    __tablename__ = "manuscript_cite_keys"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"))
    bibtex: Mapped[str] = mapped_column(Text)
    pinned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptSnapshot(Base):
    __tablename__ = "manuscript_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(Text)  # compile | autosave | before_restore | before_sections
    files: Mapped[dict[str, str]] = mapped_column(JSONB)  # {path: text}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptEvidence(Base):
    """One paper's passages and verdict for one sentence of a manuscript (hash: sha256 of its plain text)."""

    __tablename__ = "manuscript_evidence"
    __table_args__ = (
        UniqueConstraint("manuscript_id", "sentence_hash", "paper_id", name="uq_manuscript_evidence_sentence_paper"),
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_evidence_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    sentence_hash: Mapped[str] = mapped_column(Text)
    sentence: Mapped[str] = mapped_column(Text)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)  # queued | running | done | failed
    verdict: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    output_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_outputs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
