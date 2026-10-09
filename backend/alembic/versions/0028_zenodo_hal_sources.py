"""paper_sources.zenodo_enabled/zenodo_api_key/hal_enabled: Zenodo and HAL join the registry as the 10th
and 11th sources (M32 batch 3). Zenodo takes an optional API token that raises its anonymous page-size
cap from 25 to 100 (confirmed live) -- same optional-key shape as CORE/PubMed/PMC. HAL takes no key at
all -- no hal_api_key column. Both on by default, like every other free source.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-09
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN zenodo_enabled boolean NOT NULL DEFAULT true",
    "ALTER TABLE paper_sources ADD COLUMN zenodo_api_key text",
    "ALTER TABLE paper_sources ADD COLUMN hal_enabled boolean NOT NULL DEFAULT true",
]

DOWNGRADE = [
    "ALTER TABLE paper_sources DROP COLUMN hal_enabled",
    "ALTER TABLE paper_sources DROP COLUMN zenodo_api_key",
    "ALTER TABLE paper_sources DROP COLUMN zenodo_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
