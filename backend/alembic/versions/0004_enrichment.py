"""enrichment: paper metadata, authors, topics

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14
"""

from alembic import op

# If another branch also adds a 0004, whichever merges second renumbers its revision and down_revision, after
# running `alembic downgrade 0003` on its own database: a database stamped with the other branch's 0004 would
# skip this migration without an error.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Tables as in brief addendum 1 §4 and §6a. papers.authors (jsonb) stays as the byline, a list of names that is never
# an identity (Q3). manual_fields lists the columns the user corrected; extraction and enrichment skip them.
UPGRADE = """
ALTER TABLE papers
  ADD COLUMN type                   text,
  ADD COLUMN is_retracted           boolean NOT NULL DEFAULT false,
  ADD COLUMN oa_status              text,
  ADD COLUMN oa_url                 text,
  ADD COLUMN cited_by_count         int,
  ADD COLUMN referenced_works_count int,
  ADD COLUMN issn                   text,
  ADD COLUMN manual_fields          text[] NOT NULL DEFAULT '{}';

CREATE TABLE authors (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  openalex_id      text UNIQUE,
  orcid            text UNIQUE,
  display_name     text NOT NULL,
  alt_names        text[] DEFAULT '{}',
  last_institution text,
  works_count      int,
  cited_by_count   int,
  h_index          int,
  topics           jsonb DEFAULT '[]',
  fetched_at       timestamptz
);

CREATE TABLE paper_authors (
  paper_id         uuid REFERENCES papers(id) ON DELETE CASCADE,
  author_id        uuid REFERENCES authors(id) ON DELETE CASCADE,
  position         int NOT NULL,
  is_corresponding boolean DEFAULT false,
  institution      text,
  PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE paper_topics (
  paper_id  uuid REFERENCES papers(id) ON DELETE CASCADE,
  source    text NOT NULL CHECK (source IN ('author','openalex','venue')),
  label     text NOT NULL,
  score     real,
  PRIMARY KEY (paper_id, source, label)
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS paper_topics, paper_authors, authors;

ALTER TABLE papers
  DROP COLUMN type,
  DROP COLUMN is_retracted,
  DROP COLUMN oa_status,
  DROP COLUMN oa_url,
  DROP COLUMN cited_by_count,
  DROP COLUMN referenced_works_count,
  DROP COLUMN issn,
  DROP COLUMN manual_fields;
"""


def _run(sql: str) -> None:
    # asyncpg prepares every statement, and a prepared statement holds one command.
    for statement in filter(str.strip, sql.split(";")):
        op.execute(statement)


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
