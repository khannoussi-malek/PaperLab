"""Papers keep volume, issue, pages, editors, PMID and PMCID.

Revision ID: 0049
Revises: 0048
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("volume", "issue", "pages", "pmid", "pmcid"):
        op.add_column("papers", sa.Column(name, sa.Text(), nullable=True))
    op.add_column("papers", sa.Column("editors", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for name in ("editors", "pmcid", "pmid", "pages", "issue", "volume"):
        op.drop_column("papers", name)
