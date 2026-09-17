"""references: a paper's references and citing works, ranked for the library

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-17
"""

from alembic import op

# D83: chained to 0009. M17 (skills) becomes 0011 and M16 (lenses) 0012. If another branch still adds a 0010,
# whichever merges second renumbers revision and down_revision, after `alembic downgrade 0009` on its own database.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

UPGRADE = [
    # References aren't papers: no chunks, no status machine (addendum §3b). Identity across fetches is any shared id.
    """
    CREATE TABLE external_refs (
      id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      s2_id             text UNIQUE,
      openalex_id       text UNIQUE,
      doi               text,
      arxiv_id          text,
      title             text NOT NULL,
      authors           jsonb NOT NULL DEFAULT '[]',
      year              int,
      venue             text,
      cited_by_count    int,
      pdf_urls          jsonb NOT NULL DEFAULT '[]',
      title_embedding   vector(768),
      title_embed_model text,
      imported_as       uuid REFERENCES papers(id) ON DELETE SET NULL,
      fetched_at        timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX external_refs_doi ON external_refs (lower(doi))",
    "CREATE INDEX external_refs_arxiv_id ON external_refs (arxiv_id)",
    """
    CREATE TABLE paper_references (
      paper_id  uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
      ref_id    uuid NOT NULL REFERENCES external_refs(id) ON DELETE CASCADE,
      direction text NOT NULL CHECK (direction IN ('cites', 'cited_by')),
      position  int NOT NULL,
      PRIMARY KEY (paper_id, ref_id, direction)
    )
    """,
    # Co-citation counts group by reference.
    "CREATE INDEX paper_references_ref ON paper_references (ref_id, direction)",
    # Notes have no vectors of their own (D81); noted_at is the note's updated_at when it was embedded.
    """
    CREATE TABLE note_embeddings (
      note_id     uuid PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
      embedding   vector(768) NOT NULL,
      embed_model text NOT NULL,
      noted_at    timestamptz NOT NULL
    )
    """,
    """
    ALTER TABLE papers
      ADD COLUMN references_state text NOT NULL DEFAULT 'none'
        CHECK (references_state IN ('none', 'fetching', 'ready', 'failed')),
      ADD COLUMN references_error text,
      ADD COLUMN references_requested_at timestamptz
    """,
]

DOWNGRADE = [
    "ALTER TABLE papers DROP COLUMN references_requested_at, DROP COLUMN references_error,"
    " DROP COLUMN references_state",
    "DROP TABLE note_embeddings",
    "DROP TABLE paper_references",
    "DROP TABLE external_refs",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
