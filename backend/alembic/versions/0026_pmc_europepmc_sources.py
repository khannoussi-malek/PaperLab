"""paper_sources.pmc_enabled/pmc_api_key/europe_pmc_enabled: PMC and Europe PMC join the registry as the
8th and 9th sources (M32 batch 2). PMC shares PubMed's NCBI E-utilities host and takes the same optional
API key (3 req/s unkeyed, 10/s keyed). Europe PMC takes no key at all -- no europe_pmc_api_key column.
Both on by default, like every other free source.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-09
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN pmc_enabled boolean NOT NULL DEFAULT true",
    "ALTER TABLE paper_sources ADD COLUMN pmc_api_key text",
    "ALTER TABLE paper_sources ADD COLUMN europe_pmc_enabled boolean NOT NULL DEFAULT true",
]

DOWNGRADE = [
    "ALTER TABLE paper_sources DROP COLUMN europe_pmc_enabled",
    "ALTER TABLE paper_sources DROP COLUMN pmc_api_key",
    "ALTER TABLE paper_sources DROP COLUMN pmc_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
