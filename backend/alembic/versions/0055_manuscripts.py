"""M27a's schema: LaTeX manuscripts kept in Postgres (manuscripts, their files, the cite keys pinned to papers, and
snapshots for restoring), compiled in the worker.

Revision ID: 0055
Revises: 0053
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID

from alembic import op

revision = "0055"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    now = sa.text("now()")
    op.create_table(
        "manuscripts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="SET NULL")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("main_file", sa.Text(), server_default="main.tex", nullable=False),
        sa.Column("checklist", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("compile_status", sa.Text(), server_default="never", nullable=False),
        sa.Column("compile_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("compile_started_at", sa.DateTime(timezone=True)),
        sa.Column("compiled_at", sa.DateTime(timezone=True)),
        sa.Column("compile_log", sa.Text()),
        sa.Column("compile_errors", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.CheckConstraint(
            "compile_status IN ('never', 'running', 'ok', 'failed')", name="ck_manuscripts_compile_status"
        ),
    )
    op.create_table(
        "manuscript_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "manuscript_id", UUID(as_uuid=True), sa.ForeignKey("manuscripts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("data", BYTEA()),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("manuscript_id", "path", name="uq_manuscript_files_path"),
        sa.CheckConstraint("(text IS NULL) <> (data IS NULL)", name="ck_manuscript_files_text_or_data"),
    )
    op.create_table(
        "manuscript_cite_keys",
        sa.Column(
            "manuscript_id", UUID(as_uuid=True), sa.ForeignKey("manuscripts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="SET NULL")),
        sa.Column("bibtex", sa.Text(), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("manuscript_id", "key"),
    )
    op.create_table(
        "manuscript_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "manuscript_id", UUID(as_uuid=True), sa.ForeignKey("manuscripts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("files", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.CheckConstraint(
            "reason IN ('compile', 'autosave', 'before_restore')", name="ck_manuscript_snapshots_reason"
        ),
    )
    op.create_index(
        "ix_manuscript_snapshots_recent", "manuscript_snapshots", ["manuscript_id", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("ix_manuscript_snapshots_recent", "manuscript_snapshots")
    op.drop_table("manuscript_snapshots")
    op.drop_table("manuscript_cite_keys")
    op.drop_table("manuscript_files")
    op.drop_table("manuscripts")
