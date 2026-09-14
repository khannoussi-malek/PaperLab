"""chat answers: question, ordered sources, whole-paper flag

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13
"""

from alembic import op

# Collision rule (D27): track B (M6.5) also adds a 0003. Whichever branch merges second renumbers
# its revision and down_revision.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE llm_outputs ADD COLUMN question text, "
        "ADD COLUMN source_chunks uuid[] NOT NULL DEFAULT '{}', "
        "ADD COLUMN whole_paper boolean NOT NULL DEFAULT false"
    )
    # Deleting a paper cascades to its answers; a note promoted from one must survive (D9).
    op.execute(
        "ALTER TABLE notes DROP CONSTRAINT notes_source_id_fkey, "
        "ADD CONSTRAINT notes_source_id_fkey FOREIGN KEY (source_id) REFERENCES llm_outputs(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE notes DROP CONSTRAINT notes_source_id_fkey, "
        "ADD CONSTRAINT notes_source_id_fkey FOREIGN KEY (source_id) REFERENCES llm_outputs(id)"
    )
    op.execute("ALTER TABLE llm_outputs DROP COLUMN question, DROP COLUMN source_chunks, DROP COLUMN whole_paper")
