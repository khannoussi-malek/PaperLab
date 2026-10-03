"""screening assist: decision times, per-hit suggestions, workspace criteria and suggestion job state

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-26
"""

from alembic import op

# M31 (D186-D190). One migration for M31a and M31b (spec §5). Chained to the head at branch cut (K21, D83).
revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE workspace_search_hits ADD COLUMN stage1_decided_at timestamptz",
    "ALTER TABLE workspace_search_hits ADD COLUMN suggestion text "
    "CHECK (suggestion IN ('include','exclude','unsure'))",
    "ALTER TABLE workspace_search_hits ADD COLUMN suggestion_reason text CHECK (suggestion_reason IN "
    "('wrong_topic','wrong_study_type','duplicate','language','inaccessible','other'))",
    "ALTER TABLE workspace_search_hits ADD COLUMN suggestion_note text",
    "ALTER TABLE workspace_search_hits ADD COLUMN suggestion_model text",
    "ALTER TABLE workspace_search_hits ADD COLUMN suggested_at timestamptz",
    "ALTER TABLE workspaces ADD COLUMN screening_criteria text",
    "ALTER TABLE workspaces ADD COLUMN screening_ranked_used boolean NOT NULL DEFAULT false",
    "ALTER TABLE workspaces ADD COLUMN suggest_status text NOT NULL DEFAULT 'idle' "
    "CHECK (suggest_status IN ('idle','running','stopping'))",
    "ALTER TABLE workspaces ADD COLUMN suggest_done integer NOT NULL DEFAULT 0",
    "ALTER TABLE workspaces ADD COLUMN suggest_total integer NOT NULL DEFAULT 0",
    "ALTER TABLE workspaces ADD COLUMN suggest_error text",
]

DOWNGRADE = [
    *(f"ALTER TABLE workspaces DROP COLUMN {c}" for c in (
        "suggest_error", "suggest_total", "suggest_done", "suggest_status", "screening_ranked_used",
        "screening_criteria",
    )),
    *(f"ALTER TABLE workspace_search_hits DROP COLUMN {c}" for c in (
        "suggested_at", "suggestion_model", "suggestion_note", "suggestion_reason", "suggestion", "stage1_decided_at",
    )),
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
