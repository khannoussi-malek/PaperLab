"""paper_sources.openreview_enabled: OpenReview joins the registry as a title-search source (M32 batch 7). It takes
no key. Off by default: its search also returns reviews and drafts, and overlaps the other conference sources.

Revision ID: 0076
Revises: 0075
Create Date: 2026-11-13
"""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

UPGRADE = ["ALTER TABLE paper_sources ADD COLUMN openreview_enabled boolean NOT NULL DEFAULT false"]

DOWNGRADE = ["ALTER TABLE paper_sources DROP COLUMN openreview_enabled"]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
