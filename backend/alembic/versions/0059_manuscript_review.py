"""The citation reviewer: its runs, the verdict on each sentence and cited paper, and dismissed sentences.

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = sa.text("now()")

    def ms_fk() -> sa.ForeignKey:
        return sa.ForeignKey("manuscripts.id", ondelete="CASCADE")

    op.create_table(
        "manuscript_review_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manuscript_id", UUID(as_uuid=True), ms_fk(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("include_uncited", sa.Boolean(), nullable=False),
        sa.Column("uncited_skipped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')", name="ck_manuscript_review_runs_status"
        ),
    )
    op.create_index("ix_manuscript_review_runs_manuscript", "manuscript_review_runs", ["manuscript_id", "created_at"])
    op.create_table(
        "manuscript_claim_checks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "manuscript_id", UUID(as_uuid=True), sa.ForeignKey("manuscripts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("manuscript_review_runs.id", ondelete="SET NULL")),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("sentence_hash", sa.Text(), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("plain", sa.Text(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("cite_key", sa.Text()),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text()),
        sa.Column("reason", sa.Text()),
        sa.Column("quote", sa.Text()),
        sa.Column("page", sa.Integer()),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="SET NULL")),
        sa.Column("output_id", UUID(as_uuid=True), sa.ForeignKey("llm_outputs.id", ondelete="SET NULL")),
        sa.Column("model", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.CheckConstraint("kind IN ('cited', 'uncited')", name="ck_manuscript_claim_checks_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_claim_checks_status"
        ),
    )
    op.create_index(
        "uq_manuscript_claim_checks_cited",
        "manuscript_claim_checks",
        ["manuscript_id", "file_path", "sentence_hash", "paper_id"],
        unique=True,
        postgresql_where=sa.text("paper_id IS NOT NULL"),
    )
    op.create_index(
        "uq_manuscript_claim_checks_uncited",
        "manuscript_claim_checks",
        ["manuscript_id", "file_path", "sentence_hash"],
        unique=True,
        postgresql_where=sa.text("paper_id IS NULL"),
    )
    op.create_index("ix_manuscript_claim_checks_file", "manuscript_claim_checks", ["manuscript_id", "file_path"])
    op.create_index("ix_manuscript_claim_checks_paper", "manuscript_claim_checks", ["paper_id"])
    op.create_table(
        "manuscript_claim_dismissals",
        sa.Column("manuscript_id", UUID(as_uuid=True), ms_fk(), primary_key=True),
        sa.Column("sentence_hash", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("manuscript_claim_dismissals")
    op.drop_table("manuscript_claim_checks")  # drops its indexes
    op.drop_table("manuscript_review_runs")
