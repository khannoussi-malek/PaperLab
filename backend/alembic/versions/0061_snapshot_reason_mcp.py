"""A snapshot taken before an MCP (Claude) edit gets its own reason.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-31
"""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

NAME = "ck_manuscript_snapshots_reason"
OLD = "reason IN ('compile', 'autosave', 'before_restore', 'before_sections')"
NEW = "reason IN ('compile', 'autosave', 'before_restore', 'before_sections', 'before_mcp')"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint(NAME, "manuscript_snapshots", type_="check")
    op.create_check_constraint(NAME, "manuscript_snapshots", NEW)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("DELETE FROM manuscript_snapshots WHERE reason = 'before_mcp'")
    op.drop_constraint(NAME, "manuscript_snapshots", type_="check")
    op.create_check_constraint(NAME, "manuscript_snapshots", OLD)
