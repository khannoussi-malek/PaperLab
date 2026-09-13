"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-13
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Written as SQL on purpose: generated tsv column, HNSW index and composite PKs read
# more clearly here than as SQLAlchemy constructs. See the project brief for the rationale
# behind each non-obvious choice before changing any of it.
UPGRADE = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE papers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doi           text UNIQUE,
  openalex_id   text UNIQUE,
  title         text NOT NULL,
  abstract      text,
  authors       jsonb DEFAULT '[]',
  year          int,
  venue         text,
  file_path     text NOT NULL,
  page_count    int,
  status        text NOT NULL DEFAULT 'uploaded',
  status_error  text,
  created_at    timestamptz DEFAULT now()
);

CREATE TABLE chunks (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id       uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  ordinal        int NOT NULL,
  page           int NOT NULL,
  bbox           jsonb NOT NULL,
  section_title  text,
  text           text NOT NULL,
  tsv            tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding      vector(768),
  embed_model    text NOT NULL,
  strategy_ver   int NOT NULL,
  UNIQUE (paper_id, ordinal)
);

-- NULLS NOT DISTINCT: without it, two root categories (parent_id NULL) could share a name.
CREATE TABLE categories (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id  uuid REFERENCES categories(id) ON DELETE CASCADE,
  name       text NOT NULL,
  UNIQUE NULLS NOT DISTINCT (parent_id, name)
);

CREATE TABLE llm_outputs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id       uuid REFERENCES papers(id) ON DELETE CASCADE,
  kind           text NOT NULL,
  content        text NOT NULL,
  cited_chunks   uuid[] DEFAULT '{}',
  model          text NOT NULL,
  prompt_version int NOT NULL,
  created_at     timestamptz DEFAULT now()
);

CREATE TABLE notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  body        text NOT NULL,
  provenance  text NOT NULL CHECK (provenance IN ('human','llm','llm_edited')),
  source_id   uuid REFERENCES llm_outputs(id),
  embedding   vector(768),
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

CREATE TABLE note_anchors (
  note_id      uuid REFERENCES notes(id) ON DELETE CASCADE,
  paper_id     uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  chunk_id     uuid REFERENCES chunks(id) ON DELETE SET NULL,
  page         int,
  bbox         jsonb,
  quoted_text  text,
  PRIMARY KEY (note_id, paper_id, page, bbox)
);

CREATE TABLE note_categories (
  note_id     uuid REFERENCES notes(id) ON DELETE CASCADE,
  category_id uuid REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (note_id, category_id)
);

CREATE TABLE paper_categories (
  paper_id    uuid REFERENCES papers(id) ON DELETE CASCADE,
  category_id uuid REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (paper_id, category_id)
);

CREATE TABLE edges (
  src_paper  uuid REFERENCES papers(id) ON DELETE CASCADE,
  dst_paper  uuid REFERENCES papers(id) ON DELETE CASCADE,
  type       text NOT NULL CHECK (type IN ('cites','concept')),
  weight     real DEFAULT 1.0,
  confirmed  boolean DEFAULT false,
  note_id    uuid REFERENCES notes(id) ON DELETE CASCADE,
  PRIMARY KEY (src_paper, dst_paper, type)
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON chunks (paper_id, page);
CREATE INDEX ON note_anchors (paper_id, page);
CREATE INDEX ON edges (dst_paper, type);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS edges, paper_categories, note_categories, note_anchors, notes,
  llm_outputs, categories, chunks, papers;
"""


def _run(sql: str) -> None:
    # asyncpg prepares every statement, and a prepared statement holds one command.
    for statement in filter(str.strip, sql.split(";")):
        op.execute(statement)


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
