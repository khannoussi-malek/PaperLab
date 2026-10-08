"""external_refs.external_ids: non-unique partial indexes for the arxiv/core keys.

references.py's _same_reference/_upsert match arXiv and CORE ids via
external_ids->>'arxiv' / ->>'core', which had no index after 0022 (that migration
only indexed openalex/semantic_scholar, since those are the only two keys with a
DB-level uniqueness requirement). An unindexed OR branch forces the whole
match query (_upsert's OR'd lookup across doi/openalex/semantic_scholar/arxiv/core)
into a sequential scan, even though the other branches are indexed — Postgres can
only build a BitmapOr plan when every OR'd condition has an index to use.

These are intentionally NON-unique: unlike openalex/semantic_scholar, arxiv/core
ids have no uniqueness guarantee (a fold-in-progress window can briefly leave
the same id on more than one row), so a unique index here would be incorrect,
not just unnecessary.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-08
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block; see 0022's upgrade()
    # for the autocommit_block() mechanism and the indisvalid recovery note.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_arxiv ON external_refs "
            "((external_ids->>'arxiv')) WHERE external_ids->>'arxiv' IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_core ON external_refs "
            "((external_ids->>'core')) WHERE external_ids->>'core' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_arxiv")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_core")
