"""Note kinds: what a note is for (a five Cs note, a summary, ...). NULL for an ordinary note.

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

KINDS = "'five_cs','summary','reconstruction','assumption','future_work','figure'"


def upgrade() -> None:
    op.add_column("notes", sa.Column("kind", sa.Text(), nullable=True))
    op.create_check_constraint("notes_kind", "notes", f"kind IN ({KINDS})")
    # a check's kept lines and dropped count, judged once when it was saved: {lines: [{verdict, text, cited}], dropped}
    op.add_column("llm_outputs", sa.Column("check_result", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_outputs", "check_result")
    op.execute("DELETE FROM llm_outputs WHERE kind = 'check'")  # older code can't read a check row
    op.drop_constraint("notes_kind", "notes", type_="check")
    op.drop_column("notes", "kind")
