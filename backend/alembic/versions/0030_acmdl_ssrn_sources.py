"""paper_sources.acm_dl_enabled/ssrn_enabled: ACM DL and SSRN join the registry as the 12th and 13th
sources (M32 batch 4). Neither takes a key -- both are Crossref/OpenAlex filtered to one publisher, so
they ride their parent's own key handling untouched; no acm_dl_api_key/ssrn_api_key column. Both on by
default, like every other free source.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-10
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN acm_dl_enabled boolean NOT NULL DEFAULT true",
    "ALTER TABLE paper_sources ADD COLUMN ssrn_enabled boolean NOT NULL DEFAULT true",
]

DOWNGRADE = [
    "ALTER TABLE paper_sources DROP COLUMN ssrn_enabled",
    "ALTER TABLE paper_sources DROP COLUMN acm_dl_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
