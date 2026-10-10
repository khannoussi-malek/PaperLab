"""external_refs partial index for the iacr_eprint external_ids key (M32 batch 6 phase A), same shape
as every prior new-key index (0025, 0027, 0029, 0033) -- workspace_search.py and references.py OR
together one condition per external_ids key, and an unindexed key forces a sequential scan (D201, D202,
D204, D206). This one is also the query search_page's own local ILIKE lookup filters on directly
(app/providers/iacr_eprint.py's own search_page), so it is load-bearing for ordinary search latency, not
just the merge-matching path every other batch's own index has served.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-10
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY external_refs_external_ids_iacr_eprint ON external_refs "
            "((external_ids->>'iacr_eprint')) WHERE external_ids->>'iacr_eprint' IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_iacr_eprint")
