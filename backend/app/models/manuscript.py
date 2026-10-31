import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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
    reason: Mapped[str] = mapped_column(Text)  # compile | autosave | before_restore | before_sections | before_mcp
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


class ManuscriptReviewRun(Base):
    """One pass of the citation reviewer over one file of a manuscript."""

    __tablename__ = "manuscript_review_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')", name="ck_manuscript_review_runs_status"
        ),
        Index("ix_manuscript_review_runs_manuscript", "manuscript_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    file_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # queued | running | done | failed | cancelled
    total: Mapped[int] = mapped_column(Integer)
    done: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    reason: Mapped[str | None] = mapped_column(Text)
    include_uncited: Mapped[bool] = mapped_column(Boolean)
    uncited_skipped: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptClaimCheck(Base):
    """The reviewer's verdict on one sentence and one cited paper (paper_id NULL: an uncited sentence)."""

    __tablename__ = "manuscript_claim_checks"
    __table_args__ = (
        CheckConstraint("kind IN ('cited', 'uncited')", name="ck_manuscript_claim_checks_kind"),
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_claim_checks_status"
        ),
        CheckConstraint(
            "(kind = 'uncited' AND paper_id IS NULL AND cite_key IS NULL) OR (kind = 'cited' AND cite_key IS NOT NULL)",
            name="ck_manuscript_claim_checks_shape",
        ),
        Index(
            "uq_manuscript_claim_checks_cited",
            "manuscript_id", "file_path", "sentence_hash", "paper_id",
            unique=True,
            postgresql_where=text("paper_id IS NOT NULL"),
        ),
        Index(  # a key that resolved to no paper (paper_id NULL): once per key; an uncited row has cite_key NULL
            "uq_manuscript_claim_checks_unresolved",
            "manuscript_id", "file_path", "sentence_hash", text("COALESCE(cite_key, '')"),
            unique=True,
            postgresql_where=text("paper_id IS NULL"),
        ),
        Index("ix_manuscript_claim_checks_file", "manuscript_id", "file_path"),
        Index("ix_manuscript_claim_checks_paper", "paper_id"),
    )  # fmt: skip

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscript_review_runs.id", ondelete="SET NULL"))
    file_path: Mapped[str] = mapped_column(Text)
    sentence_hash: Mapped[str] = mapped_column(Text)
    sentence: Mapped[str] = mapped_column(Text)  # the raw source sentence, whitespace-normalised
    plain: Mapped[str] = mapped_column(Text)
    ord: Mapped[int] = mapped_column(Integer)  # document order
    kind: Mapped[str] = mapped_column(Text)  # cited | uncited
    cite_key: Mapped[str | None] = mapped_column(Text)
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text)  # queued | running | done | failed
    verdict: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    output_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_outputs.id", ondelete="SET NULL"))
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptClaimDismissal(Base):
    """A sentence the researcher waved off: the reviewer stops flagging it."""

    __tablename__ = "manuscript_claim_dismissals"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"), primary_key=True)
    sentence_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
