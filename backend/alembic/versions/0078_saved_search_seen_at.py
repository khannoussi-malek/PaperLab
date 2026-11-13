"""saved_searches.seen_at: when the reader last looked at what a saved search found (M7.6 inbox)

Existing rows start at now(), so hits found before the inbox existed don't all arrive as new at once.

Revision ID: 0078
Revises: 0077
Create Date: 2026-11-13
"""

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE saved_searches ADD COLUMN seen_at timestamptz NOT NULL DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE saved_searches DROP COLUMN seen_at")
