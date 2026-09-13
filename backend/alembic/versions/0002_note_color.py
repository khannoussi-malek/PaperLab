"""note highlight colour

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Lowercase #rrggbb; the API lowercases before it gets here. Existing notes become yellow.
    op.execute(
        "ALTER TABLE notes ADD COLUMN color text NOT NULL DEFAULT '#facc15' "
        "CONSTRAINT notes_color_hex CHECK (color ~ '^#[0-9a-f]{6}$')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE notes DROP COLUMN color")
