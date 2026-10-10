"""external_refs partial indexes for the zenodo and hal external_ids keys (M32 batch 3), same shape as
0025's pubmed index and 0027's pmc index -- workspace_search.py and references.py OR together one
condition per external_ids key, and an unindexed key forces a sequential scan.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-10
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_zenodo ON external_refs "
            "((external_ids->>'zenodo')) WHERE external_ids->>'zenodo' IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_hal ON external_refs "
            "((external_ids->>'hal')) WHERE external_ids->>'hal' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_hal")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_zenodo")
