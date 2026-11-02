"""The Settings switch for hybrid search: fuse a keyword ranking with the vectors across papers. Off until turned on.

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-02
"""

import sqlalchemy as sa

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    column = sa.Column("hybrid_search", sa.Boolean(), server_default=sa.false(), nullable=False)
    op.add_column("embedding_source", column)


def downgrade() -> None:
    op.drop_column("embedding_source", "hybrid_search")
