"""search_run_eligibility

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-24
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE search_run_eligibility (
        paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        search_run_id uuid NOT NULL REFERENCES workspace_search_runs(id) ON DELETE CASCADE,
        stage2_status text,
        stage2_exclude_reason text,
        assessed_at timestamptz,
        PRIMARY KEY (paper_id, search_run_id),
        CHECK (stage2_status IN ('include','exclude'))
    )
    """,
]

DOWNGRADE = [
    "DROP TABLE search_run_eligibility",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
