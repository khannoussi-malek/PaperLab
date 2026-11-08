"""How each search hit reached a workspace (snowball tree): one link per path, plus per-branch decisions."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkspaceHitLink(Base):
    __tablename__ = "workspace_hit_links"
    __table_args__ = (
        CheckConstraint("kind IN ('search', 'cites', 'cited_by')", name="ck_workspace_hit_links_kind"),
        UniqueConstraint(
            "child_hit_id", "parent_hit_id", "parent_paper_id", "kind", "run_id",
            name="uq_workspace_hit_links_path", postgresql_nulls_not_distinct=True,
        ),
        Index("ix_workspace_hit_links_workspace_id", "workspace_id"),
        Index("ix_workspace_hit_links_parent_hit_id", "parent_hit_id"),
        Index("ix_workspace_hit_links_parent_paper_id", "parent_paper_id"),
        Index("ix_workspace_hit_links_run_id", "run_id"),
        Index(
            "ix_workspace_hit_links_workspace_id_non_search", "workspace_id", postgresql_where=text("kind <> 'search'")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    child_hit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace_search_hits.id", ondelete="CASCADE"))
    parent_hit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace_search_hits.id", ondelete="CASCADE"), default=None
    )
    parent_paper_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), default=None
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace_search_runs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class WorkspaceBranchState(Base):
    __tablename__ = "workspace_branch_states"
    __table_args__ = (
        CheckConstraint("state IN ('go_further', 'stopped')", name="ck_workspace_branch_states_state"),
        CheckConstraint("(hit_id IS NULL) <> (paper_id IS NULL)", name="ck_workspace_branch_states_one_target"),
        CheckConstraint("set_by IN ('screening', 'owner')", name="ck_workspace_branch_states_set_by"),
        UniqueConstraint(
            "workspace_id", "hit_id", "paper_id",
            name="uq_workspace_branch_states_target", postgresql_nulls_not_distinct=True,
        ),
        Index("ix_workspace_branch_states_hit_id", "hit_id"),
        Index("ix_workspace_branch_states_paper_id", "paper_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    hit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace_search_hits.id", ondelete="CASCADE"), default=None
    )
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), default=None)
    state: Mapped[str] = mapped_column(String)
    directions: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    # 'screening' rows follow the paper's screening decision; 'owner' rows are a hand choice and stay put.
    set_by: Mapped[str] = mapped_column(String, server_default=text("'owner'"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
