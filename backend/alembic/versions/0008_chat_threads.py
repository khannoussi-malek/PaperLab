"""chat threads: the answer a follow-up continues

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-16
"""

from alembic import op

# If another branch also adds a 0008 (M17's skills was planned there), whichever merges second renumbers revision and
# down_revision, after running `alembic downgrade 0007` on its own database: a database stamped with the other
# branch's 0008 would skip this migration without an error.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UPGRADE = [
    # Deleting an answer turns its follow-ups into the start of their own threads, never a dangling id.
    "ALTER TABLE llm_outputs ADD COLUMN parent_id uuid REFERENCES llm_outputs(id) ON DELETE SET NULL",
    # Deleting a paper deletes its answers; without an index each one scans llm_outputs for follow-ups to update.
    "CREATE INDEX llm_outputs_parent_id ON llm_outputs (parent_id)",
]

DOWNGRADE = [
    "DROP INDEX llm_outputs_parent_id",
    "ALTER TABLE llm_outputs DROP COLUMN parent_id",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
