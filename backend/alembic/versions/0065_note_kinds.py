"""Note kinds: what a note is for (a five Cs note, a summary, ...). NULL for an ordinary note.

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-02
"""

import sqlalchemy as sa

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

KINDS = "'five_cs','summary','reconstruction','assumption','future_work','figure'"


def upgrade() -> None:
    op.add_column("notes", sa.Column("kind", sa.Text(), nullable=True))
    op.create_check_constraint("notes_kind", "notes", f"kind IN ({KINDS})")


def downgrade() -> None:
    op.drop_constraint("notes_kind", "notes", type_="check")
    op.drop_column("notes", "kind")
