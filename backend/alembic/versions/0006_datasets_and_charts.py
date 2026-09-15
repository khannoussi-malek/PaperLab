"""datasets and charts: numbers captured from papers or typed in, and charts that point at them

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-14
"""

from alembic import op

# If another branch also adds a 0006, whichever merges second renumbers revision and down_revision, after running
# `alembic downgrade 0005` on its own database: a database stamped with the other branch's 0006 would skip this
# migration without an error.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE = [
    # A dataset is a table: a captured table, the numbers picked from one paper's text, or the owner's own data.
    # Deleting its paper keeps it (the owner's work), with paper_id NULL.
    """
    CREATE TABLE datasets (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      name       text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
      kind       text NOT NULL CHECK (kind IN ('table', 'numbers', 'user')),
      paper_id   uuid REFERENCES papers(id) ON DELETE SET NULL,
      page       int,
      region     jsonb,
      extractor  text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX datasets_paper_id_idx ON datasets (paper_id)",
    "CREATE UNIQUE INDEX datasets_one_numbers_dataset_per_paper ON datasets (paper_id) WHERE kind = 'numbers'",
    # Rows and columns have their own ids so a chart keeps pointing at the same data when positions change.
    """
    CREATE TABLE dataset_columns (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      dataset_id uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
      position   int NOT NULL,
      name       text NOT NULL DEFAULT '',
      unit       text
    )
    """,
    "CREATE INDEX dataset_columns_dataset_id_idx ON dataset_columns (dataset_id)",
    """
    CREATE TABLE dataset_rows (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      dataset_id uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
      position   int NOT NULL
    )
    """,
    "CREATE INDEX dataset_rows_dataset_id_idx ON dataset_rows (dataset_id)",
    # raw is what the paper (or the owner) wrote; value and error are parsed from it. original_raw keeps the extracted
    # text once the owner changes an extracted cell. bbox is a list of rects in PDF points, like note anchors.
    """
    CREATE TABLE cells (
      row_id       uuid NOT NULL REFERENCES dataset_rows(id) ON DELETE CASCADE,
      column_id    uuid NOT NULL REFERENCES dataset_columns(id) ON DELETE CASCADE,
      raw          text NOT NULL DEFAULT '',
      value        double precision,
      error        double precision,
      origin       text NOT NULL CHECK (origin IN ('extracted', 'human')),
      original_raw text,
      page         int,
      bbox         jsonb,
      PRIMARY KEY (row_id, column_id)
    )
    """,
    "CREATE INDEX cells_column_id_idx ON cells (column_id)",
    # A chart stores a versioned spec that names column and row ids, never copied numbers.
    """
    CREATE TABLE charts (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      title        text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
      spec         jsonb NOT NULL,
      spec_version int NOT NULL,
      created_at   timestamptz NOT NULL DEFAULT now(),
      updated_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE chart_datasets (
      chart_id   uuid REFERENCES charts(id) ON DELETE CASCADE,
      dataset_id uuid REFERENCES datasets(id) ON DELETE CASCADE,
      PRIMARY KEY (chart_id, dataset_id)
    )
    """,
    "CREATE INDEX chart_datasets_dataset_id_idx ON chart_datasets (dataset_id)",
    """
    CREATE TABLE note_charts (
      note_id  uuid REFERENCES notes(id) ON DELETE CASCADE,
      chart_id uuid REFERENCES charts(id) ON DELETE CASCADE,
      PRIMARY KEY (note_id, chart_id)
    )
    """,
    "CREATE INDEX note_charts_chart_id_idx ON note_charts (chart_id)",
]

DOWNGRADE = [
    "DROP TABLE note_charts",
    "DROP TABLE chart_datasets",
    "DROP TABLE charts",
    "DROP TABLE cells",
    "DROP TABLE dataset_rows",
    "DROP TABLE dataset_columns",
    "DROP TABLE datasets",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
