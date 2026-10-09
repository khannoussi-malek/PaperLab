"""external_refs.external_ids: a non-unique partial index for the pubmed key, same reasoning as 0023's
arxiv/core indexes — _find_or_create_external_ref/_same_reference OR together one condition per source
key in candidate.external_ids, and Postgres can only build a BitmapOr plan when every OR'd branch has an
index. PubMed joined the registry in 0024 with no matching index, which turns any OR query that includes
a pubmed id into a sequential scan (confirmed via EXPLAIN on the dev database: ~1,337 cost with an index,
~7,768 without).

Non-unique, same reasoning as 0023's arxiv/core indexes: a fold-in-progress window can briefly leave the
same id recorded on more than one row, so a unique index here would be incorrect, not just unnecessary.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-09
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block; see 0022's upgrade() for the
    # autocommit_block() mechanism and the indisvalid recovery note.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_pubmed ON external_refs "
            "((external_ids->>'pubmed')) WHERE external_ids->>'pubmed' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_pubmed")
