"""mcp_activity: the log of tool calls Claude made on the library, and the owner's switch for changes (M36)

Revision ID: 0073
Revises: 0072
Create Date: 2026-11-13
"""

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE mcp_activity (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      at          timestamptz NOT NULL DEFAULT now(),
      tool        text NOT NULL,
      arguments   text NOT NULL,
      outcome     text NOT NULL,
      duration_ms integer NOT NULL,
      is_write    boolean NOT NULL
    )
    """,
    "CREATE INDEX mcp_activity_at ON mcp_activity (at)",
    # A singleton, like paper_sources: the CHECK refuses any id but true.
    """
    CREATE TABLE mcp_settings (
      id            boolean PRIMARY KEY DEFAULT true CHECK (id),
      writes_enabled boolean NOT NULL DEFAULT true
    )
    """,
    "INSERT INTO mcp_settings (id) VALUES (true)",
]

DOWNGRADE = [
    "DROP TABLE mcp_settings",
    "DROP TABLE mcp_activity",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
