from datetime import datetime

from sqlalchemy import DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Setup(Base):
    """The one row (id true) saying whether the first-run setup is done: Finish or Skip, in the app (spec §5)."""

    __tablename__ = "setup"

    id: Mapped[bool] = mapped_column(primary_key=True, server_default=text("true"))
    done: Mapped[bool]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
