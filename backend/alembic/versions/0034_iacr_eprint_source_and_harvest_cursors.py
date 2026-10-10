"""paper_sources.iacr_eprint_enabled: IACR ePrint joins the registry as the 16th source (M32 batch 6
phase A) -- no key, IACR's own OAI-PMH endpoint needs none. Also creates harvest_cursors, a new,
deliberately tiny table tracking each periodic-harvest source's own last-synced point so a restarted
job resumes instead of re-harvesting IACR's full 28,110-record archive (confirmed live, 2026-10-10)
from 1996 every time. Not reusing any existing cursor table (workspace_search_cursors) since that one
is scoped to one Workspace Search run at a time; this one is global per harvest source, independent of
any run.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-10
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN iacr_eprint_enabled boolean NOT NULL DEFAULT true",
    """
    CREATE TABLE harvest_cursors (
        source text PRIMARY KEY,
        last_synced_at timestamptz,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
]

DOWNGRADE = [
    "DROP TABLE harvest_cursors",
    "ALTER TABLE paper_sources DROP COLUMN iacr_eprint_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
