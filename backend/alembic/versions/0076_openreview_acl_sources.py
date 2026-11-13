"""paper_sources.openreview_enabled and acl_anthology_enabled: OpenReview (M32 batch 7) takes no key and is off by
default: its search also returns reviews and drafts, and overlaps the other conference sources. ACL Anthology is on by
default: it receives nothing from a search, since its public metadata file is harvested weekly.

Also for the ACL harvest: harvest_cursors gets etag and last_modified, so a weekly run sends If-None-Match and a 304
leaves the stored rows and cursor alone (harvest_cursors had no state column to hold them). A GIN index on
external_refs.external_ids lets harvest_ingest_candidate's per-record lookup and the ACL search's key test use an
index instead of scanning every reference; built CONCURRENTLY, like 0022's index.

Revision ID: 0076
Revises: 0075
Create Date: 2026-11-13
"""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_sources ADD COLUMN openreview_enabled boolean NOT NULL DEFAULT false",
    "ALTER TABLE paper_sources ADD COLUMN acl_anthology_enabled boolean NOT NULL DEFAULT true",
    "ALTER TABLE harvest_cursors ADD COLUMN etag text",
    "ALTER TABLE harvest_cursors ADD COLUMN last_modified text",
]

DOWNGRADE = [
    "ALTER TABLE harvest_cursors DROP COLUMN last_modified",
    "ALTER TABLE harvest_cursors DROP COLUMN etag",
    "ALTER TABLE paper_sources DROP COLUMN acl_anthology_enabled",
    "ALTER TABLE paper_sources DROP COLUMN openreview_enabled",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block; autocommit_block() commits the migration's
    # transaction for this one statement, the same mechanism 0022 uses.
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY external_refs_external_ids_gin ON external_refs USING gin (external_ids)")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS external_refs_external_ids_gin")
    for statement in DOWNGRADE:
        op.execute(statement)
