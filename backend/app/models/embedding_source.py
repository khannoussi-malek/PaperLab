import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmbeddingSource(Base):
    """The one row (id true) saying which source search embeds with (D151). No row: Built-in. The connection holds the
    key; nothing here is ever returned by a route as it is (core/embedding_sources.SourceView)."""

    __tablename__ = "embedding_source"

    id: Mapped[bool] = mapped_column(primary_key=True, server_default=text("true"))
    kind: Mapped[str] = mapped_column(Text)  # builtin | ollama | openai | gemini | openai_compatible
    connection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_connections.id"))
    model: Mapped[str | None] = mapped_column(Text)
    # D156: the name the last switch or re-index rebuilds toward, and when it started.
    rebuild_model: Mapped[str | None] = mapped_column(Text)
    rebuild_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # D155: the last embedding failure as shown to the owner (masked, never a key).
    error: Mapped[str | None] = mapped_column(Text)
    error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
