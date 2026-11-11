"""Claude's edits log which tool, path and reason on their snapshot.

Revision ID: 0069
Revises: 0068
"""

import sqlalchemy as sa

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manuscript_snapshots", sa.Column("ai_tool", sa.Text(), nullable=True))
    op.add_column("manuscript_snapshots", sa.Column("ai_path", sa.Text(), nullable=True))
    op.add_column("manuscript_snapshots", sa.Column("ai_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("manuscript_snapshots", "ai_reason")
    op.drop_column("manuscript_snapshots", "ai_path")
    op.drop_column("manuscript_snapshots", "ai_tool")
