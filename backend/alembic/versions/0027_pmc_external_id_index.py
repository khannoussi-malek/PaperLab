"""external_refs.external_ids: a non-unique partial index for the pmc key, same reasoning as 0025's
pubmed index -- _find_or_create_external_ref/_same_reference OR together one condition per source key in
candidate.external_ids, and Postgres can only build a BitmapOr plan when every OR'd branch has an index.
PMC joined the registry in 0026 with no matching index, which turns any OR query that includes a pmc id
into a sequential scan (confirmed via EXPLAIN on the dev database: Seq Scan, cost 7771.84, for a query
ORing a pmc and a pubmed condition).

Non-unique, same reasoning as 0023/0025: a fold-in-progress window can briefly leave the same id recorded
on more than one row, so a unique index here would be incorrect, not just unnecessary.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-09
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_pmc ON external_refs "
            "((external_ids->>'pmc')) WHERE external_ids->>'pmc' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_pmc")
