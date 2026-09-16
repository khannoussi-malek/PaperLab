import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LLMOutput(Base):
    __tablename__ = "llm_outputs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    question: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    # C{i} is source_chunks[i-1]. No FK on array elements: a re-ingest deletes chunks, and their
    # markers then render as plain text.
    source_chunks: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default=text("'{}'"))
    cited_chunks: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default=text("'{}'"))
    # A chat answer has exactly one of paper_id / workspace_id (CHECK llm_outputs_chat_scope).
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    # N{i} is source_notes[i-1]. No FK on array elements: a deleted note renders as plain text.
    source_notes: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default=text("'{}'"))
    notes_used: Mapped[int | None]  # notes that fit the budget; NULL on paper answers from before prompt v2
    notes_total: Mapped[int | None]
    whole_paper: Mapped[bool] = mapped_column(server_default=text("false"))
    model: Mapped[str] = mapped_column(Text)
    # The connection's label when the answer was written, copied (no FK): renaming or deleting the connection
    # never changes it. NULL for answers written before connections existed.
    connection_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
