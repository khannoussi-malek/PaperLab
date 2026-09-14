"""workspaces: flat categories with shared papers, and workspace chat answers

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14
"""

from alembic import op

# Numbered after 0004 (enrichment), which reached main first. If this is ever renumbered again, move revision and
# down_revision, the upgrade target in tests/test_invariants.py's data test, and run `alembic downgrade` to the new
# down_revision on any database stamped with the old number first: a database stamped with another branch's
# revision would otherwise skip this migration without an error.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE categories RENAME TO workspaces",
    "ALTER TABLE workspaces RENAME CONSTRAINT categories_pkey TO workspaces_pkey",
    # Names were unique per parent. No UI ever created categories, but never fail on old data:
    # the second and later rows sharing a name get " (2)", " (3)"…, roots first.
    # ponytail: a suffixed name can still collide with an existing "Thesis (2)"; nothing has such rows.
    """
    UPDATE workspaces w SET name = w.name || ' (' || d.n || ')'
    FROM (SELECT id, row_number() OVER (PARTITION BY name ORDER BY parent_id NULLS FIRST, id) AS n FROM workspaces) d
    WHERE w.id = d.id AND d.n > 1
    """,
    # Dropping parent_id also drops its FK and the (parent_id, name) unique constraint.
    "ALTER TABLE workspaces DROP COLUMN parent_id, ADD COLUMN created_at timestamptz DEFAULT now(), "
    "ADD CONSTRAINT workspaces_name_key UNIQUE (name)",
    "ALTER TABLE paper_categories RENAME TO workspace_papers",
    "ALTER TABLE workspace_papers RENAME COLUMN category_id TO workspace_id",
    "ALTER TABLE workspace_papers RENAME CONSTRAINT paper_categories_pkey TO workspace_papers_pkey",
    "ALTER TABLE workspace_papers RENAME CONSTRAINT paper_categories_paper_id_fkey TO workspace_papers_paper_id_fkey",
    "ALTER TABLE workspace_papers RENAME CONSTRAINT paper_categories_category_id_fkey "
    "TO workspace_papers_workspace_id_fkey",
    "ALTER TABLE workspace_papers ADD COLUMN added_at timestamptz DEFAULT now()",
    "DROP TABLE note_categories",
    # NULL arrays become empty before NOT NULL. source_chunks is NOT NULL since 0003.
    "UPDATE llm_outputs SET cited_chunks = '{}' WHERE cited_chunks IS NULL",
    "ALTER TABLE llm_outputs ALTER COLUMN cited_chunks SET NOT NULL, "
    "ADD COLUMN workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE, "
    "ADD COLUMN notes_used int, ADD COLUMN notes_total int, "
    "ADD COLUMN source_notes uuid[] NOT NULL DEFAULT '{}', "
    # A chat answer belongs to exactly one scope: a paper or a workspace.
    "ADD CONSTRAINT llm_outputs_chat_scope CHECK (kind <> 'chat' OR (paper_id IS NULL) <> (workspace_id IS NULL))",
]

DOWNGRADE = [
    # The older schema has nowhere to keep a workspace answer.
    "DELETE FROM llm_outputs WHERE workspace_id IS NOT NULL",
    "ALTER TABLE llm_outputs DROP CONSTRAINT llm_outputs_chat_scope, DROP COLUMN workspace_id, "
    "DROP COLUMN notes_used, DROP COLUMN notes_total, DROP COLUMN source_notes, "
    "ALTER COLUMN cited_chunks DROP NOT NULL",
    "ALTER TABLE workspace_papers DROP COLUMN added_at",
    "ALTER TABLE workspace_papers RENAME CONSTRAINT workspace_papers_workspace_id_fkey "
    "TO paper_categories_category_id_fkey",
    "ALTER TABLE workspace_papers RENAME CONSTRAINT workspace_papers_paper_id_fkey TO paper_categories_paper_id_fkey",
    "ALTER TABLE workspace_papers RENAME CONSTRAINT workspace_papers_pkey TO paper_categories_pkey",
    "ALTER TABLE workspace_papers RENAME COLUMN workspace_id TO category_id",
    "ALTER TABLE workspace_papers RENAME TO paper_categories",
    "ALTER TABLE workspaces RENAME TO categories",
    "ALTER TABLE categories RENAME CONSTRAINT workspaces_pkey TO categories_pkey",
    "ALTER TABLE categories DROP CONSTRAINT workspaces_name_key, DROP COLUMN created_at, "
    "ADD COLUMN parent_id uuid REFERENCES categories(id) ON DELETE CASCADE, "
    "ADD UNIQUE NULLS NOT DISTINCT (parent_id, name)",
    """
    CREATE TABLE note_categories (
      note_id     uuid REFERENCES notes(id) ON DELETE CASCADE,
      category_id uuid REFERENCES categories(id) ON DELETE CASCADE,
      PRIMARY KEY (note_id, category_id)
    )
    """,
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
