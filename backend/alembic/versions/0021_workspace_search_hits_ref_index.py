"""a plain index on workspace_search_hits.external_ref_id

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-04
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The existing workspace_search_hits_unique_ref index is (workspace_id, external_ref_id) — unusable for a
    # lookup on external_ref_id alone, which is exactly what this column's own ON DELETE SET NULL foreign key
    # needs every time a row is deleted from external_refs. Without this, that delete forces a full sequential
    # scan of workspace_search_hits per deleted row — confirmed directly via EXPLAIN, and the actual cause of a
    # single DELETE FROM external_refs taking 10+ minutes once that table reached ~38k rows.
    op.create_index("ix_workspace_search_hits_external_ref_id", "workspace_search_hits", ["external_ref_id"])


def downgrade() -> None:
    op.drop_index("ix_workspace_search_hits_external_ref_id", "workspace_search_hits")
