"""llm_outputs.readings: the per-paper records (kind 'paper_reading') an Ask each paper answer was written from (M8.5)

Revision ID: 0083
Revises: 0082
Create Date: 2026-11-23
"""

from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_outputs ADD COLUMN readings uuid[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE llm_outputs DROP COLUMN readings")
