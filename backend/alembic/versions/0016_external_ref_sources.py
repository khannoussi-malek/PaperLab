"""external_refs.sources

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-24
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE external_refs ADD COLUMN sources jsonb NOT NULL DEFAULT '[]'",
]

DOWNGRADE = [
    "ALTER TABLE external_refs DROP COLUMN sources",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
