"""Whole-draft review runs (S2P B7).

Revision ID: 0070
Revises: 0069
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manuscript_draft_reviews",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("manuscript_id", sa.Uuid(), sa.ForeignKey("manuscripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.Text(), server_default="light", nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text()),
        sa.Column("calls_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("calls_max", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("inputs", JSONB(), nullable=False),
        sa.Column("issues", JSONB()),
        sa.Column("refuted", JSONB()),
        sa.Column("counts", JSONB()),
        sa.Column("confirm_remote", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("model", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_draft_reviews_status"
        ),
        sa.CheckConstraint("mode IN ('light', 'full')", name="ck_manuscript_draft_reviews_mode"),
    )
    op.create_index(
        "ix_manuscript_draft_reviews_manuscript", "manuscript_draft_reviews", ["manuscript_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("manuscript_draft_reviews")
