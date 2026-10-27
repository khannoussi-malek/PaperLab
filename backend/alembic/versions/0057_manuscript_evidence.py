"""Evidence for a manuscript's sentences: the papers that speak to one and each paper's verdict.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = sa.text("now()")
    op.create_table(
        "manuscript_evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "manuscript_id", UUID(as_uuid=True), sa.ForeignKey("manuscripts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("sentence_hash", sa.Text(), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text()),
        sa.Column("reason", sa.Text()),
        sa.Column("quote", sa.Text()),
        sa.Column("page", sa.Integer()),
        sa.Column("output_id", UUID(as_uuid=True), sa.ForeignKey("llm_outputs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("manuscript_id", "sentence_hash", "paper_id", name="uq_manuscript_evidence_sentence_paper"),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_manuscript_evidence_status"),
    )
    op.create_index("ix_manuscript_evidence_paper", "manuscript_evidence", ["paper_id"])


def downgrade() -> None:
    op.drop_index("ix_manuscript_evidence_paper", "manuscript_evidence")
    op.drop_table("manuscript_evidence")
