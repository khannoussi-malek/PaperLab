"""answer_snapshot: an answer keeps a copy of the passages it cited, so [C#] survives a re-ingest (M33)

Revision ID: 0074
Revises: 0073
Create Date: 2026-11-13
"""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

# Nullable and not backfilled: an answer saved before M33 has no snapshot, and its passages are never guessed.
UPGRADE = ["ALTER TABLE llm_outputs ADD COLUMN source_snapshot jsonb"]

DOWNGRADE = ["ALTER TABLE llm_outputs DROP COLUMN source_snapshot"]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
