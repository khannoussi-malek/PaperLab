import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VoiceTurn(Base):
    """How long each stage of one spoken question took, in ms. Kept when its paper or workspace is deleted."""

    __tablename__ = "voice_turns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(Text)
    connection_name: Mapped[str | None] = mapped_column(Text)
    cold: Mapped[bool]  # the first question after the microphone was turned on (the program warms itself at start)
    whole_paper: Mapped[bool]
    interrupted: Mapped[bool] = mapped_column(server_default=text("false"))
    false_interrupt: Mapped[bool] = mapped_column(server_default=text("false"))
    # Measured here, from when the utterance arrived.
    stt_ms: Mapped[int | None]
    retrieval_ms: Mapped[int | None]
    embed_ms: Mapped[int | None]  # null when a small paper went whole with no search
    prompt_chars: Mapped[int | None]
    ttft_ms: Mapped[int | None]
    first_chunk_ms: Mapped[int | None]
    tts_first_ms: Mapped[int | None]
    first_audio_sent_ms: Mapped[int | None]
    # Reported by the page.
    wait_ms: Mapped[int | None]
    output_ms: Mapped[int | None]
    total_ms: Mapped[int | None]
    interrupt_stop_ms: Mapped[int | None]
