"""paper links: the links the owner draws between two papers, and dropping the unused edges table

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-17
"""

from alembic import op

# D110: chained to 0010. Every other derived link kind stays derived (D88/D106); this table holds the one kind
# nothing can derive.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE paper_links (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      from_paper uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
      to_paper   uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
      label      text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT paper_links_two_papers CHECK (from_paper <> to_paper)
    )
    """,
    # One link per pair whichever way it was drawn.
    "CREATE UNIQUE INDEX paper_links_pair ON paper_links (least(from_paper, to_paper), greatest(from_paper, to_paper))",
    # The graph reads a paper's links from either end.
    "CREATE INDEX paper_links_to ON paper_links (to_paper)",
    # Empty since 0001, with a CHECK allowing only 'cites'/'concept'. Derived links are never stored (D88), and the
    # owner's own links live in paper_links, so nothing writes here.
    "DROP TABLE edges",
]

DOWNGRADE = [
    """
    CREATE TABLE edges (
      src_paper  uuid REFERENCES papers(id) ON DELETE CASCADE,
      dst_paper  uuid REFERENCES papers(id) ON DELETE CASCADE,
      type       text NOT NULL CHECK (type IN ('cites','concept')),
      weight     real DEFAULT 1.0,
      confirmed  boolean DEFAULT false,
      note_id    uuid REFERENCES notes(id) ON DELETE CASCADE,
      PRIMARY KEY (src_paper, dst_paper, type)
    )
    """,
    "CREATE INDEX ON edges (dst_paper, type)",
    "DROP TABLE paper_links",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
