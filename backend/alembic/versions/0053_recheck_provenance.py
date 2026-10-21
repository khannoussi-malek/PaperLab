"""PR 4's schema: when a PDF-less paper was last checked for a free copy and what came of it, which source last filled
each group of a paper's details (field_sources), the weekly re-check's switch, and paper_events, a paper's history.

Revision ID: 0053
Revises: 0052
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("pdf_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("papers", sa.Column("pdf_check_result", sa.Text(), nullable=True))
    op.create_check_constraint("ck_papers_pdf_check_result", "papers", "pdf_check_result IN ('found', 'none', 'error')")
    # No backfill (R22): existing papers start with no known source. Values are checked in Python (ProvenanceSource).
    op.add_column("papers", sa.Column("field_sources", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column(
        "paper_sources",
        sa.Column("pdf_recheck_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_table(
        "paper_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('pdf_found', 'pdf_attached')", name="ck_paper_events_kind"),
    )
    op.create_index("ix_paper_events_paper_id", "paper_events", ["paper_id"])
    op.create_index("ix_paper_events_kind_seen_at", "paper_events", ["kind", "seen_at"])  # the unseen finds


def downgrade() -> None:
    # ponytail: refuse rather than lose a paper's history
    if op.get_bind().execute(sa.text("SELECT 1 FROM paper_events LIMIT 1")).first():
        raise RuntimeError("paper events are recorded; delete them first")
    op.drop_table("paper_events")
    op.drop_column("paper_sources", "pdf_recheck_enabled")
    op.drop_column("papers", "field_sources")
    op.drop_constraint("ck_papers_pdf_check_result", "papers")
    op.drop_column("papers", "pdf_check_result")
    op.drop_column("papers", "pdf_checked_at")
