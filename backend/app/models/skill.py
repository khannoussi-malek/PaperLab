import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Skill(Base):
    """A reader's change to a bundled skill (builtin_slug set) or a custom skill (builtin_slug null). Its rules and
    the partial unique indexes that keep one default per chat kind are in migration 0072."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    builtin_slug: Mapped[str | None] = mapped_column(Text, unique=True)
    # Null on a bundled row means "the shipped value"; a custom row sets all four.
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)  # null = the shipped text
    lens: Mapped[str | None] = mapped_column(Text)  # null = the shipped lens (a bundled skill) or 'full' (a custom one)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    is_listed: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_paper_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_workspace_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
