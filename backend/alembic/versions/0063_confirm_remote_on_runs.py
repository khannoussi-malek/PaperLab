"""Keep the researcher's yes to a remote model on citation-check runs and evidence rows, so the job checks it again.

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-31
"""

import sqlalchemy as sa

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

TABLES = ("manuscript_review_runs", "manuscript_evidence")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("confirm_remote", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "confirm_remote")
