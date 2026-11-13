"""workspace_read_only: an imported workspace is read-only until its owner makes it editable (M35b1)

Revision ID: 0075
Revises: 0074
Create Date: 2026-11-13
"""

from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

# Existing workspaces stay editable: only an import sets the flag, and only Make it editable clears it.
UPGRADE = ["ALTER TABLE workspaces ADD COLUMN read_only boolean NOT NULL DEFAULT false"]

DOWNGRADE = ["ALTER TABLE workspaces DROP COLUMN read_only"]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
