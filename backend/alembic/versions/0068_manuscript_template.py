"""A manuscript remembers the template it was made from ('custom' for imports and older manuscripts).

Revision ID: 0068
Revises: 0067
"""

import sqlalchemy as sa

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manuscripts", sa.Column("template", sa.Text(), server_default="custom", nullable=False))


def downgrade() -> None:
    op.drop_column("manuscripts", "template")
