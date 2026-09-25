"""note papers: a note's papers, whole or with passages, and which answer block a saved suggestion came from

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25
"""

from alembic import op

# M20 (D95, D96). Chained to the head when the branch was cut (K21, D83): never 0011, which is paper_links (D110).
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE note_papers (
      note_id  uuid NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
      paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
      PRIMARY KEY (note_id, paper_id)
    )
    """,
    # "A paper's notes" is read by paper everywhere (reader, workspaces, chat, graph).
    "CREATE INDEX note_papers_paper_id ON note_papers (paper_id)",
    # Every note and paper a passage already joins becomes a link.
    "INSERT INTO note_papers (note_id, paper_id) SELECT DISTINCT note_id, paper_id FROM note_anchors",
    # A passage only on a linked paper; taking a paper off a note removes its passages there (N2). The existing
    # foreign keys stay.
    "ALTER TABLE note_anchors ADD CONSTRAINT note_anchors_note_paper_fkey FOREIGN KEY (note_id, paper_id) "
    "REFERENCES note_papers (note_id, paper_id) ON DELETE CASCADE",
    "ALTER TABLE notes ADD COLUMN source_block smallint",
    # One note per block of one answer. No CHECK ties it to source_id: deleting the answer sets source_id NULL (0003),
    # and a CHECK would make that delete fail.
    "CREATE UNIQUE INDEX notes_source_block ON notes (source_id, source_block) WHERE source_block IS NOT NULL",
]

DOWNGRADE = [
    "DROP INDEX notes_source_block",
    "ALTER TABLE notes DROP COLUMN source_block",
    "ALTER TABLE note_anchors DROP CONSTRAINT note_anchors_note_paper_fkey",
    "DROP TABLE note_papers",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
