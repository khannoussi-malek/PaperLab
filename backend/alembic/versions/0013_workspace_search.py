"""workspace search: runs, cursors, hits; external_refs.core_id

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-23
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    ALTER TABLE external_refs ADD COLUMN core_id text
    """,
    """
    CREATE TABLE workspace_search_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        query_text text NOT NULL,
        query_overrides_json jsonb NOT NULL DEFAULT '{}',
        filters_json jsonb NOT NULL DEFAULT '{}',
        sources_json jsonb NOT NULL,
        status text NOT NULL CHECK (status IN ('running','stopped','exhausted','failed')),
        started_at timestamptz NOT NULL DEFAULT now(),
        stopped_at timestamptz,
        stats_json jsonb NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE workspace_search_cursors (
        run_id uuid NOT NULL REFERENCES workspace_search_runs(id) ON DELETE CASCADE,
        source text NOT NULL,
        cursor_json jsonb NOT NULL DEFAULT '{}',
        exhausted boolean NOT NULL DEFAULT false,
        last_error text,
        PRIMARY KEY (run_id, source)
    )
    """,
    """
    CREATE TABLE workspace_search_hits (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        run_id uuid NOT NULL REFERENCES workspace_search_runs(id) ON DELETE CASCADE,
        external_ref_id uuid REFERENCES external_refs(id) ON DELETE SET NULL,
        source_method text NOT NULL CHECK (source_method IN
            ('database_search','snowball_backward','snowball_forward')),
        seed_paper_id uuid REFERENCES papers(id) ON DELETE SET NULL,
        snowball_round int,
        normalized_title text NOT NULL,
        first_seen_at timestamptz NOT NULL DEFAULT now(),
        stage1_status text CHECK (stage1_status IN ('relevant','not_relevant','maybe')),
        stage1_exclude_reason text CHECK (stage1_exclude_reason IN
            ('wrong_topic','wrong_study_type','duplicate','language','inaccessible','other')),
        stage1_note text,
        priority smallint CHECK (priority BETWEEN 1 AND 5),
        topic_fit text CHECK (topic_fit IN
            ('same_topic','related_topic','different_topic','out_of_scope')),
        acquisition_status text NOT NULL DEFAULT 'not_attempted' CHECK (acquisition_status IN
            ('not_attempted','queued','imported','failed','manual')),
        paper_id uuid REFERENCES papers(id) ON DELETE SET NULL,
        CONSTRAINT workspace_search_hits_unique_ref UNIQUE (workspace_id, external_ref_id)
    )
    """,
    "CREATE INDEX ON workspace_search_hits (workspace_id, stage1_status)",
    "CREATE INDEX ON workspace_search_hits (run_id)",
    "CREATE INDEX ON workspace_search_hits (workspace_id, first_seen_at, id)",
]

DOWNGRADE = [
    "DROP TABLE workspace_search_hits",
    "DROP TABLE workspace_search_cursors",
    "DROP TABLE workspace_search_runs",
    "ALTER TABLE external_refs DROP COLUMN core_id",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
