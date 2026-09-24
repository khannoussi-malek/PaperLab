"""external_refs.abstract

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-24
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE external_refs ADD COLUMN abstract text",
]

DOWNGRADE = [
    "ALTER TABLE external_refs DROP COLUMN abstract",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
