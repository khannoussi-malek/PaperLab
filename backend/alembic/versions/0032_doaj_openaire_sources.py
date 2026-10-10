"""paper_sources.doaj_enabled/openaire_enabled: DOAJ and OpenAIRE join the registry as the 14th and
15th sources (M32 batch 5). Neither takes a key -- DOAJ's own docs confirm a key only raises write
limits, never search; OpenAIRE's higher tier needs an hourly-refreshing OAuth2 token this codebase has
no machinery for, and anonymous access already gets a generous rate limit in practice (confirmed live,
2026-10-10). Both on by default, like every other free source.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-10
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN doaj_enabled boolean NOT NULL DEFAULT true",
    "ALTER TABLE paper_sources ADD COLUMN openaire_enabled boolean NOT NULL DEFAULT true",
]

DOWNGRADE = [
    "ALTER TABLE paper_sources DROP COLUMN openaire_enabled",
    "ALTER TABLE paper_sources DROP COLUMN doaj_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
