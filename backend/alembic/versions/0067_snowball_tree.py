"""Snowball tree: record how each search hit was found (links) and per-branch decisions (branch states).

Revision ID: 0067
Revises: 0066
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


# One-time backfill of links for hits found before the tables existed (tests run this very list). Idempotent.
# A paper seed's parent is the earliest hit carrying that paper; with no such hit the paper itself is the parent.
# Snowball hits with no seed_paper_id (seeded from a hit, not recorded) get no link. Each link is dated when
# its hit was first seen.
BACKFILL_SQL: list[str] = [
    """
    INSERT INTO workspace_hit_links (workspace_id, child_hit_id, run_id, kind, created_at)
    SELECT workspace_id, id, run_id, 'search', first_seen_at
    FROM workspace_search_hits WHERE source_method = 'database_search'
    ON CONFLICT DO NOTHING
    """,
    """
    WITH seed_hit AS (
        SELECT DISTINCT ON (workspace_id, paper_id) workspace_id, paper_id, id
        FROM workspace_search_hits WHERE paper_id IS NOT NULL
        ORDER BY workspace_id, paper_id, first_seen_at, id
    )
    INSERT INTO workspace_hit_links
        (workspace_id, child_hit_id, parent_hit_id, parent_paper_id, run_id, kind, created_at)
    SELECT h.workspace_id, h.id, p.id, CASE WHEN p.id IS NULL THEN h.seed_paper_id END, h.run_id,
           CASE h.source_method WHEN 'snowball_backward' THEN 'cites' ELSE 'cited_by' END, h.first_seen_at
    FROM workspace_search_hits h
    LEFT JOIN seed_hit p ON p.workspace_id = h.workspace_id AND p.paper_id = h.seed_paper_id
    WHERE h.source_method IN ('snowball_backward', 'snowball_forward') AND h.seed_paper_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """,
]


def _fk(column: str, target: str, ondelete: str, nullable: bool = False) -> sa.Column:
    return sa.Column(column, pg.UUID, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "workspace_hit_links",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _fk("workspace_id", "workspaces.id", "CASCADE"),
        _fk("child_hit_id", "workspace_search_hits.id", "CASCADE"),
        _fk("parent_hit_id", "workspace_search_hits.id", "CASCADE", nullable=True),
        _fk("parent_paper_id", "papers.id", "CASCADE", nullable=True),
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
    op.create_index("ix_workspace_hit_links_parent_paper_id", "workspace_hit_links", ["parent_paper_id"])
    op.create_index("ix_workspace_hit_links_run_id", "workspace_hit_links", ["run_id"])
    # for the snowball tree's default scope (everything that is not a plain search hit)
    op.create_index(
        "ix_workspace_hit_links_workspace_id_non_search", "workspace_hit_links", ["workspace_id"],
        postgresql_where=sa.text("kind <> 'search'"),
    )
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
    op.create_index("ix_workspace_branch_states_hit_id", "workspace_branch_states", ["hit_id"])
    op.create_index("ix_workspace_branch_states_paper_id", "workspace_branch_states", ["paper_id"])
    for statement in BACKFILL_SQL:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("workspace_branch_states")
    op.drop_table("workspace_hit_links")
