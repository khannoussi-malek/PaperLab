"""Section operations (add, rename, move, delete, split) snapshot first, under their own reason.

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-27
"""

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

NAME = "ck_manuscript_snapshots_reason"
OLD = "reason IN ('compile', 'autosave', 'before_restore')"
NEW = "reason IN ('compile', 'autosave', 'before_restore', 'before_sections')"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint(NAME, "manuscript_snapshots", type_="check")
    op.create_check_constraint(NAME, "manuscript_snapshots", NEW)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("DELETE FROM manuscript_snapshots WHERE reason = 'before_sections'")
    op.drop_constraint(NAME, "manuscript_snapshots", type_="check")
    op.create_check_constraint(NAME, "manuscript_snapshots", OLD)
