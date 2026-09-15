"""model connections: where chat models come from, which models chat lists, and the connection each answer used

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-15
"""

from alembic import op

# If another branch also adds a 0007, whichever merges second renumbers revision and down_revision, after running
# `alembic downgrade 0006` on its own database: a database stamped with the other branch's 0007 would skip this
# migration without an error.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UPGRADE = [
    # One row per place models come from. The key is plain text, the same exposure as .env; no route returns it.
    """
    CREATE TABLE llm_connections (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      kind       text NOT NULL CHECK (kind IN ('ollama', 'anthropic', 'openai_compatible')),
      label      text NOT NULL UNIQUE CHECK (length(btrim(label)) BETWEEN 1 AND 80),
      base_url   text,
      api_key    text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # The models chat lists: only the ones the owner added, since some providers list hundreds.
    """
    CREATE TABLE llm_models (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      connection_id uuid NOT NULL REFERENCES llm_connections(id) ON DELETE CASCADE,
      name          text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
      is_default    boolean NOT NULL DEFAULT false,
      UNIQUE (connection_id, name)
    )
    """,
    # At most one default, guaranteed by the database: every true row has the same key.
    "CREATE UNIQUE INDEX llm_models_one_default ON llm_models ((is_default)) WHERE is_default",
    # The connection's name when the answer was written, copied: renaming or deleting it never changes an answer.
    "ALTER TABLE llm_outputs ADD COLUMN connection_name text",
]

DOWNGRADE = [
    "ALTER TABLE llm_outputs DROP COLUMN connection_name",
    "DROP TABLE llm_models",
    "DROP TABLE llm_connections",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
