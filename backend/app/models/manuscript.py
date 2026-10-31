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
    confirm_remote: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # re-checked by the job
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
    confirm_remote: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # re-checked by the job
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


ROLES = "'abstract', 'intro', 'related', 'method', 'results', 'discussion', 'limitations', 'conclusion'"


class ManuscriptSectionReview(Base):
    """The AI's check of one section against what its role needs; it judges and never writes text."""

    __tablename__ = "manuscript_section_reviews"
    __table_args__ = (
        CheckConstraint(f"role IN ({ROLES})", name="ck_manuscript_section_reviews_role"),
        CheckConstraint("role_source IN ('guessed', 'chosen')", name="ck_manuscript_section_reviews_role_source"),
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_section_reviews_status"
        ),
        UniqueConstraint("manuscript_id", "file_path", "section_hash", name="uq_manuscript_section_reviews_section"),
        Index("ix_manuscript_section_reviews_file", "manuscript_id", "file_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    file_path: Mapped[str] = mapped_column(Text)
    section_hash: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    role_source: Mapped[str] = mapped_column(Text)  # guessed | chosen
    status: Mapped[str] = mapped_column(Text)  # queued | running | done | failed
    source: Mapped[str] = mapped_column(Text)  # the section's text as of base, at most 60 000 chars
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)  # {"sentences": [...], "notes": [...]}
    findings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)  # [{"kind", "point", "refs"}]
    dropped: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    confirm_remote: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # re-checked by the job
    reason: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ManuscriptDiagram(Base):
    """A TikZ picture generated from the researcher's own description; inserted only on a click."""

    __tablename__ = "manuscript_diagrams"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_diagrams_status"),
        Index("ix_manuscript_diagrams_manuscript", "manuscript_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # queued | running | done | failed
    code: Mapped[str | None] = mapped_column(Text)  # the picture only
    libraries: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    compiled: Mapped[bool | None] = mapped_column(Boolean)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    labels_not_in_description: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    preview_pdf: Mapped[bytes | None] = mapped_column(LargeBinary)  # at most 300 KB
    reason: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[int | None] = mapped_column(Integer)
    confirm_remote: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # re-checked by the job
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
