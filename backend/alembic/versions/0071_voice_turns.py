"""Voice turns: the timing of each spoken question, kept after its paper is deleted.

Revision ID: 0071
Revises: 0070
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

MEASURES = (
    "stt_ms",
    "retrieval_ms",
    "embed_ms",
    "prompt_chars",
    "ttft_ms",
    "first_chunk_ms",
    "tts_first_ms",
    "first_audio_sent_ms",
    "wait_ms",
    "output_ms",
    "total_ms",
    "interrupt_stop_ms",
)


def upgrade() -> None:
    op.create_table(
        "voice_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="SET NULL")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="SET NULL")),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("connection_name", sa.Text()),
        sa.Column("cold", sa.Boolean(), nullable=False),
        sa.Column("whole_paper", sa.Boolean(), nullable=False),
        sa.Column("interrupted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("false_interrupt", sa.Boolean(), server_default=sa.false(), nullable=False),
        *(sa.Column(name, sa.Integer()) for name in MEASURES),
    )


def downgrade() -> None:
    op.drop_table("voice_turns")
