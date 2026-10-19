"""paper_merges: the history of papers merged into the paper saved without a PDF that is the same work, and of the
merges only reported (R16). No FKs, so a row outlives both papers.

Revision ID: 0052
Revises: 0051
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_merges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kept_id", UUID(as_uuid=True), nullable=False),
        sa.Column("merged_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("moved", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('merged', 'reported')", name="ck_paper_merges_status"),
    )


def downgrade() -> None:
    # ponytail: refuse rather than lose the only record of which paper became which
    if op.get_bind().execute(sa.text("SELECT 1 FROM paper_merges LIMIT 1")).first():
        raise RuntimeError("paper merges are recorded; delete them first")
    op.drop_table("paper_merges")
