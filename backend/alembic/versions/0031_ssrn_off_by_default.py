"""paper_sources.ssrn_enabled: 0030 landed SSRN on by default, like every other free source. The final
review (M32 batch 4 fix round) found SSRN isn't actually free -- it rides OpenAlex's own client, so it
competes with OpenAlex for OpenAlex's metered, cost-bearing quota. Same policy as openalex_enabled (P3):
the only sources on by default are ones that can't cost money, so SSRN's column default flips to false,
matching its registry entry. New rows only -- not touching the owner's already-seeded row, which this
project's migrations have never done for a default-only change.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-10
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE paper_sources ALTER COLUMN ssrn_enabled SET DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE paper_sources ALTER COLUMN ssrn_enabled SET DEFAULT true")
