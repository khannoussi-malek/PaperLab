"""section role overrides: the reader's own section roles, and the lens an output was written from

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-25
"""

from alembic import op

# K21: renumbered to follow main's 0057 (manuscript evidence). If another migration lands on main first, renumber again:
# the file, revision, down_revision, this docstring and test_invariants.py's downgrade target.
revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

UPGRADE = [
    # D48: roles are computed on request; only the reader's fixes are stored, keyed on the exact heading text.
    """
    CREATE TABLE section_role_overrides (
      paper_id      uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
      section_title text NOT NULL,
      role          text NOT NULL CHECK (role IN ('abstract', 'intro', 'related', 'method', 'results', 'discussion',
                                                  'limitations', 'conclusion', 'back', 'other')),
      updated_at    timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (paper_id, section_title)
    )
    """,
    # D50: a brief's lens. Chat answers stay 'full' until lens chat lands (D56, D178).
    "ALTER TABLE llm_outputs ADD COLUMN lens text NOT NULL DEFAULT 'full'",
]

DOWNGRADE = [
    "ALTER TABLE llm_outputs DROP COLUMN lens",
    "DROP TABLE section_role_overrides",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
