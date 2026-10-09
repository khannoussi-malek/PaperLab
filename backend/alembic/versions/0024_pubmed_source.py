"""paper_sources.pubmed_enabled/pubmed_api_key: PubMed joins the registry as a 6th source (M32 batch 1).
PubMed works without a key (3 req/s); a free NCBI key raises that to 10 req/s, so it gets an optional key
slot like OpenAlex/Semantic Scholar/CORE, on by default like every other free source.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-09
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN pubmed_enabled boolean NOT NULL DEFAULT true",
    "ALTER TABLE paper_sources ADD COLUMN pubmed_api_key text",
]

DOWNGRADE = [
    "ALTER TABLE paper_sources DROP COLUMN pubmed_api_key",
    "ALTER TABLE paper_sources DROP COLUMN pubmed_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
