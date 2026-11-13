"""cells.origin may be 'llm': a cell a model wrote, such as an AI-suggested number's label (D33)

Revision ID: 0080
Revises: 0079
Create Date: 2026-11-13
"""

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cells DROP CONSTRAINT cells_origin_check")
    op.execute("ALTER TABLE cells ADD CONSTRAINT cells_origin_check CHECK (origin IN ('extracted', 'human', 'llm'))")


def downgrade() -> None:
    op.execute("UPDATE cells SET origin = 'human' WHERE origin = 'llm'")
    op.execute("ALTER TABLE cells DROP CONSTRAINT cells_origin_check")
    op.execute("ALTER TABLE cells ADD CONSTRAINT cells_origin_check CHECK (origin IN ('extracted', 'human'))")
