"""embedding source: which source search embeds with, the rebuild a switch starts, and the last embedding failure

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-24
"""

from alembic import op

# K21: the next free revision when M25's branch was cut, chained to the head then. If another branch takes this number
# first, renumber the file, revision, down_revision and this docstring.
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UPGRADE = [
    # D151. One row: the primary key can only be true. No row means Built-in, so a fresh install and an upgraded
    # library need no seed. Keys stay in llm_connections; NO ACTION refuses deleting a connection search uses.
    """
    CREATE TABLE embedding_source (
      id                 boolean PRIMARY KEY DEFAULT true CHECK (id),
      kind               text NOT NULL CHECK (kind IN ('builtin','ollama','openai','gemini','openai_compatible')),
      connection_id      uuid REFERENCES llm_connections(id),
      model              text,
      rebuild_model      text,
      rebuild_started_at timestamptz,
      error              text,
      error_at           timestamptz,
      updated_at         timestamptz NOT NULL DEFAULT now(),
      CHECK ((kind = 'builtin') = (connection_id IS NULL)),
      CHECK ((kind = 'builtin') = (model IS NULL))
    )
    """,
]

DOWNGRADE = [
    "DROP TABLE embedding_source",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
