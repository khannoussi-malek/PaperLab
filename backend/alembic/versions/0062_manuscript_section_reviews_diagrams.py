"""Section reviews (the AI checks a section against its role) and TikZ diagrams.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

ROLES = "'abstract', 'intro', 'related', 'method', 'results', 'discussion', 'limitations', 'conclusion'"


def upgrade() -> None:
    now = sa.text("now()")
    empty = sa.text("'[]'::jsonb")

    def ms_fk() -> sa.ForeignKey:
        return sa.ForeignKey("manuscripts.id", ondelete="CASCADE")

    op.create_table(
        "manuscript_section_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manuscript_id", UUID(as_uuid=True), ms_fk(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("section_hash", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("role_source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("inputs", JSONB(), nullable=False),
        sa.Column("findings", JSONB()),
        sa.Column("dropped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("confirm_remote", sa.Boolean(), server_default=sa.false(), nullable=False),  # the yes, for the job
        sa.Column("reason", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.CheckConstraint(f"role IN ({ROLES})", name="ck_manuscript_section_reviews_role"),
        sa.CheckConstraint("role_source IN ('guessed', 'chosen')", name="ck_manuscript_section_reviews_role_source"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_section_reviews_status"
        ),
        sa.UniqueConstraint("manuscript_id", "file_path", "section_hash", name="uq_manuscript_section_reviews_section"),
    )
    op.create_index("ix_manuscript_section_reviews_file", "manuscript_section_reviews", ["manuscript_id", "file_path"])
    op.create_table(
        "manuscript_diagrams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manuscript_id", UUID(as_uuid=True), ms_fk(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("code", sa.Text()),
        sa.Column("libraries", JSONB(), server_default=empty, nullable=False),
        sa.Column("compiled", sa.Boolean()),
        sa.Column("errors", JSONB(), server_default=empty, nullable=False),
        sa.Column("labels_not_in_description", JSONB(), server_default=empty, nullable=False),
        sa.Column("preview_pdf", sa.LargeBinary()),
        sa.Column("reason", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("prompt_version", sa.Integer()),
        sa.Column("confirm_remote", sa.Boolean(), server_default=sa.false(), nullable=False),  # the yes, for the job
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_diagrams_status"),
    )
    op.create_index("ix_manuscript_diagrams_manuscript", "manuscript_diagrams", ["manuscript_id", "created_at"])


def downgrade() -> None:
    op.drop_table("manuscript_diagrams")
    op.drop_table("manuscript_section_reviews")
