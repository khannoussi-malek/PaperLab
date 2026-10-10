"""Upgrades 0035's own partial index on external_ids->>'iacr_eprint' from non-unique to UNIQUE (M32 batch6a
final review, fix 7). harvest_ingest_candidate's own find-or-create lookup (app/workers/harvest.py) calls
scalar_one_or_none() on this key, assuming at most one row per id -- a duplicate (e.g. two concurrent
harvest workers racing the same insert) would make every future harvest run raise MultipleResultsFound
and fail permanently. Confirmed live on 2026-10-10: all 27,272 currently-harvested rows already have zero
duplicate iacr_eprint keys, so this upgrade is safe to apply now.

Correction to 0035's own docstring: it claimed this index is "load-bearing for ordinary search latency,"
i.e. used by search_page's own ORDER BY id LIMIT query. Confirmed live via EXPLAIN that the planner does
NOT use this index for that query -- it's only actually used by harvest_ingest_candidate's own
find-or-create lookup (the role every other new-key index in this project already plays). 0035 is not
renamed or edited after the fact; this note stands in for that correction.

Follows 0022's own established CREATE UNIQUE INDEX CONCURRENTLY precedent (autocommit_block() wrapping,
since CONCURRENTLY cannot run inside alembic's own per-migration transaction).

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-10
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_iacr_eprint")
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY external_refs_external_ids_iacr_eprint ON external_refs "
            "((external_ids->>'iacr_eprint')) WHERE external_ids->>'iacr_eprint' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_iacr_eprint")
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_iacr_eprint ON external_refs "
            "((external_ids->>'iacr_eprint')) WHERE external_ids->>'iacr_eprint' IS NOT NULL"
        )
