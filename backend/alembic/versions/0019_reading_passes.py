"""reading passes: a paper's passes finished and the reader's decision, and a To read mark on references

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

# K21: the next free revision when M21's branch was cut, chained to the head then (0018, M20's note_papers).
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # D119: set only by the reader, through PUT /api/papers/{id}/reading. Not manual_fields, not a workspace.
    op.add_column("papers", sa.Column("reading_pass", sa.SmallInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("papers_reading_pass_range", "papers", "reading_pass BETWEEN 0 AND 3")
    op.add_column("papers", sa.Column("triage", sa.Text()))
    op.create_check_constraint("papers_triage_value", "papers", "triage IN ('keep', 'later', 'drop')")
    # D120: To read lives on the shared reference row, which survives a Refresh. ponytail: no index; at library scale
    # a scan of external_refs for queued_at IS NOT NULL costs nothing. Add a partial index past ~50k references.
    op.add_column("external_refs", sa.Column("queued_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    # The CHECKs go with their columns.
    op.drop_column("external_refs", "queued_at")
    op.drop_column("papers", "triage")
    op.drop_column("papers", "reading_pass")
