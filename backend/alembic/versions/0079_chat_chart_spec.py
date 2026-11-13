"""llm_outputs.chart_spec: a chat answer that is a chart carries its spec (M14 charts in chat)

The spec names dataset, column and row ids, never numbers, the same shape a saved chart stores.

Revision ID: 0079
Revises: 0078
Create Date: 2026-11-13
"""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_outputs ADD COLUMN chart_spec jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE llm_outputs DROP COLUMN chart_spec")
