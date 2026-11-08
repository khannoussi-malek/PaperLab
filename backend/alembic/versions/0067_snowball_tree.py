"""Snowball tree: record how each search hit was found (links) and per-branch decisions (branch states).

Revision ID: 0067
Revises: 0066
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from app.models.provenance import BACKFILL_SQL

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def _fk(column: str, target: str, ondelete: str, nullable: bool = False) -> sa.Column:
    return sa.Column(column, pg.UUID, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "workspace_hit_links",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _fk("workspace_id", "workspaces.id", "CASCADE"),
        _fk("child_hit_id", "workspace_search_hits.id", "CASCADE"),
        _fk("parent_hit_id", "workspace_search_hits.id", "CASCADE", nullable=True),
        _fk("parent_paper_id", "papers.id", "SET NULL", nullable=True),
        _fk("run_id", "workspace_search_runs.id", "CASCADE"),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("created_at", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('search', 'cites', 'cited_by')", name="ck_workspace_hit_links_kind"),
        sa.UniqueConstraint(
            "child_hit_id", "parent_hit_id", "parent_paper_id", "kind", "run_id",
            name="uq_workspace_hit_links_path", postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_workspace_hit_links_workspace_id", "workspace_hit_links", ["workspace_id"])
    op.create_index("ix_workspace_hit_links_parent_hit_id", "workspace_hit_links", ["parent_hit_id"])
    op.create_table(
        "workspace_branch_states",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _fk("workspace_id", "workspaces.id", "CASCADE"),
        _fk("hit_id", "workspace_search_hits.id", "CASCADE", nullable=True),
        _fk("paper_id", "papers.id", "CASCADE", nullable=True),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("directions", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reason", sa.Text),
        sa.Column("set_by", sa.String, nullable=False, server_default=sa.text("'owner'")),
        sa.Column("updated_at", pg.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("state IN ('go_further', 'stopped')", name="ck_workspace_branch_states_state"),
        sa.CheckConstraint("(hit_id IS NULL) <> (paper_id IS NULL)", name="ck_workspace_branch_states_one_target"),
        sa.CheckConstraint("set_by IN ('screening', 'owner')", name="ck_workspace_branch_states_set_by"),
        sa.UniqueConstraint(
            "workspace_id", "hit_id", "paper_id",
            name="uq_workspace_branch_states_target", postgresql_nulls_not_distinct=True,
        ),
    )
    for statement in BACKFILL_SQL:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("workspace_branch_states")
    op.drop_table("workspace_hit_links")
