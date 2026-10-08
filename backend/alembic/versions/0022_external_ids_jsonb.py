"""external_refs.external_ids: a generic per-source identifier map, replacing one column per source (Phase 0b).
Additive only — s2_id/openalex_id/arxiv_id/core_id stay in place, unused by new code, until a later migration
drops them once this has run clean for a verification window.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-03
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE external_refs ADD COLUMN external_ids jsonb NOT NULL DEFAULT '{}'",
    """
    UPDATE external_refs SET external_ids = jsonb_strip_nulls(jsonb_build_object(
        'openalex', openalex_id, 'semantic_scholar', s2_id, 'arxiv', arxiv_id, 'core', core_id
    ))
    """,
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block; alembic/env.py wraps the whole migration
    # run in one (context.begin_transaction()). autocommit_block() commits that transaction temporarily so these
    # two statements run outside it, then resumes — the first use of this mechanism in this codebase. A run
    # interrupted here can leave an index marked invalid (pg_index.indisvalid = false); Step 4 below checks for
    # that and DROP INDEX + retry is the recovery if it ever happens.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY external_refs_external_ids_openalex ON external_refs "
            "((external_ids->>'openalex')) WHERE external_ids->>'openalex' IS NOT NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY external_refs_external_ids_semantic_scholar ON external_refs "
            "((external_ids->>'semantic_scholar')) WHERE external_ids->>'semantic_scholar' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_openalex")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_semantic_scholar")
    op.execute("ALTER TABLE external_refs DROP COLUMN external_ids")
