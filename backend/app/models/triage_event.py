import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TriageEvent(Base):
    """One reading decision on a paper (triage desk, D119): append-only history. `papers.triage` / `reading_pass`
    stay the source of truth. An undo row (source 'undo') names the event it undoes. Goes with its paper."""

    __tablename__ = "triage_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID | None]
    client_id: Mapped[uuid.UUID | None]  # the retry key: unique within a session
    source: Mapped[str] = mapped_column(Text)  # desk | reader | library | undo
    pile: Mapped[str | None] = mapped_column(Text)  # read_closely | skim | later | not_relevant | skip
    before_triage: Mapped[str | None] = mapped_column(Text)  # keep | later | drop
    after_triage: Mapped[str | None] = mapped_column(Text)
    before_pass: Mapped[int] = mapped_column(SmallInteger)
    after_pass: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    fivecs: Mapped[int | None] = mapped_column(SmallInteger)
    pdf_opened: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    pdf_ms: Mapped[int | None] = mapped_column(Integer)
    card_ms: Mapped[int | None] = mapped_column(Integer)
    undone_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("triage_events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("source IN ('desk', 'reader', 'library', 'undo')", name="ck_triage_events_source"),
        CheckConstraint(
            "pile IN ('read_closely', 'skim', 'later', 'not_relevant', 'skip')", name="ck_triage_events_pile"
        ),
        CheckConstraint("before_triage IN ('keep', 'later', 'drop')", name="ck_triage_events_before_triage"),
        CheckConstraint("after_triage IN ('keep', 'later', 'drop')", name="ck_triage_events_after_triage"),
        CheckConstraint("before_pass BETWEEN 0 AND 3", name="ck_triage_events_before_pass"),
        CheckConstraint("after_pass BETWEEN 0 AND 3", name="ck_triage_events_after_pass"),
        CheckConstraint("char_length(note) <= 500", name="ck_triage_events_note"),
        CheckConstraint("fivecs BETWEEN 0 AND 31", name="ck_triage_events_fivecs"),
        CheckConstraint("pdf_ms >= 0", name="ck_triage_events_pdf_ms"),
        CheckConstraint("card_ms >= 0", name="ck_triage_events_card_ms"),
        # a desk drop says why; an undo row (pile NULL) passes by design
        CheckConstraint(
            "pile IS DISTINCT FROM 'not_relevant' OR reason IS NOT NULL OR source <> 'desk'",
            name="ck_triage_events_drop_reason",
        ),
        CheckConstraint("(source = 'undo') = (undone_event_id IS NOT NULL)", name="ck_triage_events_undo_target"),
        Index("ix_triage_events_paper_created", "paper_id", text("created_at DESC")),
        Index("ix_triage_events_session_created", "session_id", "created_at"),
        Index(
            "uq_triage_events_undone",
            "undone_event_id",
            unique=True,
            postgresql_where=text("undone_event_id IS NOT NULL"),
        ),
        Index(
            "uq_triage_events_session_client",
            "session_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
        ),
    )
