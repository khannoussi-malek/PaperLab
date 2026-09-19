"""setup: whether the first-run setup is done, one row, preset for a library that already has papers

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-18
"""

from alembic import op

# K21: the next free revision when M24's branch was cut, chained to the head then (0011, paper_links; M23 added none).
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UPGRADE = [
    # One row: the primary key can only be true (the paper_sources pattern). Finish and Skip set done; nothing unsets
    # it but a test.
    """
    CREATE TABLE setup (
      id         boolean PRIMARY KEY DEFAULT true CHECK (id),
      done       boolean NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # An existing library (the owner's, a contributor's dev stack) never sees the first-run page.
    "INSERT INTO setup (done) SELECT EXISTS (SELECT 1 FROM papers)",
]

DOWNGRADE = [
    "DROP TABLE setup",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
