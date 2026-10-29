"""The triage desk's history: triage_events, one row per reading decision (append-only, goes with its paper).

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    triage = "('keep', 'later', 'drop')"
    op.create_table(
        "triage_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("pile", sa.Text(), nullable=True),
        sa.Column("before_triage", sa.Text(), nullable=True),
        sa.Column("after_triage", sa.Text(), nullable=True),
        sa.Column("before_pass", sa.SmallInteger(), nullable=False),
        sa.Column("after_pass", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("fivecs", sa.SmallInteger(), nullable=True),
        sa.Column("pdf_opened", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pdf_ms", sa.Integer(), nullable=True),
        sa.Column("card_ms", sa.Integer(), nullable=True),
        sa.Column("undone_event_id", UUID(as_uuid=True), sa.ForeignKey("triage_events.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('desk', 'reader', 'library', 'undo')", name="ck_triage_events_source"),
        sa.CheckConstraint(
            "pile IN ('read_closely', 'skim', 'later', 'not_relevant', 'skip')", name="ck_triage_events_pile"
        ),
        sa.CheckConstraint(f"before_triage IN {triage}", name="ck_triage_events_before_triage"),
        sa.CheckConstraint(f"after_triage IN {triage}", name="ck_triage_events_after_triage"),
        sa.CheckConstraint("before_pass BETWEEN 0 AND 3", name="ck_triage_events_before_pass"),
        sa.CheckConstraint("after_pass BETWEEN 0 AND 3", name="ck_triage_events_after_pass"),
        sa.CheckConstraint("char_length(note) <= 500", name="ck_triage_events_note"),
        sa.CheckConstraint("fivecs BETWEEN 0 AND 31", name="ck_triage_events_fivecs"),
        sa.CheckConstraint("pdf_ms >= 0", name="ck_triage_events_pdf_ms"),
        sa.CheckConstraint("card_ms >= 0", name="ck_triage_events_card_ms"),
        sa.CheckConstraint(
            "pile IS DISTINCT FROM 'not_relevant' OR reason IS NOT NULL OR source <> 'desk'",
            name="ck_triage_events_drop_reason",
        ),
        sa.CheckConstraint("(source = 'undo') = (undone_event_id IS NOT NULL)", name="ck_triage_events_undo_target"),
    )
    op.create_index("ix_triage_events_paper_created", "triage_events", ["paper_id", sa.text("created_at DESC")])
    op.create_index("ix_triage_events_session_created", "triage_events", ["session_id", "created_at"])
    op.create_index(
        "uq_triage_events_undone",
        "triage_events",
        ["undone_event_id"],
        unique=True,
        postgresql_where=sa.text("undone_event_id IS NOT NULL"),
    )
    op.create_index(
        "uq_triage_events_session_client",
        "triage_events",
        ["session_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("triage_events")
