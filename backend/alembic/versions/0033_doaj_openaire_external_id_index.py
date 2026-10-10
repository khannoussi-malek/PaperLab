"""external_refs partial indexes for the doaj and openaire external_ids keys (M32 batch 5), same shape
as 0025's pubmed index, 0027's pmc index and 0029's zenodo/hal indexes -- workspace_search.py and
references.py OR together one condition per external_ids key, and an unindexed key forces a sequential
scan (D201, D202, D204).

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-10
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_doaj ON external_refs "
            "((external_ids->>'doaj')) WHERE external_ids->>'doaj' IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_openaire ON external_refs "
            "((external_ids->>'openaire')) WHERE external_ids->>'openaire' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_openaire")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_doaj")
