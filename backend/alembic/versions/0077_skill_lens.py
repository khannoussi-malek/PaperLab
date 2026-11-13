"""skills.lens: a skill can read through a reading lens (M16 lens chat)

Null is the shipped lens for a bundled skill and 'full' for a custom one, so a bundled skill's row needs no value of its
own until the reader changes it. The CHECK keeps the column to the lens ids core/lenses.py defines.

Revision ID: 0077
Revises: 0076
Create Date: 2026-11-13
"""

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE skills ADD COLUMN lens text",
    # Bundled rows made before 0077 start at 1; the shipped texts are now v2, so a first custom text would record v2
    # too. Moving them up one keeps a reader's own text a version apart from the shipped one.
    "UPDATE skills SET version = version + 1 WHERE builtin_slug IS NOT NULL AND instructions IS NULL",
    "ALTER TABLE skills ADD CONSTRAINT skills_lens_known "
    "CHECK (lens IS NULL OR lens IN ('full', 'key_ideas', 'critical', 'method', 'related'))",
]

DOWNGRADE = [
    "ALTER TABLE skills DROP CONSTRAINT skills_lens_known",
    "ALTER TABLE skills DROP COLUMN lens",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
