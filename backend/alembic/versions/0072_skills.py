"""skills: the reader's changes to the bundled skills, and the custom ones; each answer's skill, copied

Revision ID: 0072
Revises: 0071
Create Date: 2026-11-13
"""

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

UPGRADE = [
    # A row exists for each bundled skill the reader has touched (builtin_slug set) and for each custom skill
    # (builtin_slug null). instructions NULL means the shipped text. Bundled skills are never deleted, only hidden.
    """
    CREATE TABLE skills (
      id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      builtin_slug         text UNIQUE,
      label                text,
      description          text,
      scope                text,
      instructions         text,
      version              integer NOT NULL DEFAULT 1,
      is_listed            boolean NOT NULL DEFAULT true,
      is_paper_default     boolean NOT NULL DEFAULT false,
      is_workspace_default boolean NOT NULL DEFAULT false,
      created_at           timestamptz NOT NULL DEFAULT now(),
      updated_at           timestamptz NOT NULL DEFAULT now(),
      CHECK (builtin_slug IS NOT NULL OR (label IS NOT NULL AND instructions IS NOT NULL AND scope IS NOT NULL)),
      CHECK (scope IN ('paper', 'workspace', 'both'))
    )
    """,
    # One default per chat kind: every true row has the same key, so a second one is refused by the database.
    "CREATE UNIQUE INDEX skills_one_paper_default ON skills (is_paper_default) WHERE is_paper_default",
    "CREATE UNIQUE INDEX skills_one_workspace_default ON skills (is_workspace_default) WHERE is_workspace_default",
    # The skill's label and version when the answer was written, copied: renaming or deleting it never changes them.
    "ALTER TABLE llm_outputs ADD COLUMN skill_label text",
    "ALTER TABLE llm_outputs ADD COLUMN skill_version integer",
]

DOWNGRADE = [
    "ALTER TABLE llm_outputs DROP COLUMN skill_version",
    "ALTER TABLE llm_outputs DROP COLUMN skill_label",
    "DROP TABLE skills",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
