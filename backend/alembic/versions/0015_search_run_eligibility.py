"""search_run_eligibility

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_run_eligibility",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspace_search_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage2_status", sa.Text(), nullable=True),
        sa.Column("stage2_exclude_reason", sa.Text(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("paper_id", "search_run_id"),
        sa.CheckConstraint("stage2_status IN ('include','exclude')", name="search_run_eligibility_status_check"),
    )


def downgrade() -> None:
    op.drop_table("search_run_eligibility")
