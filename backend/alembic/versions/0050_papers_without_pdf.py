"""Papers can exist without a PDF: file_path may be NULL, and details_source says where the details came from.

Revision ID: 0050
Revises: 0049
"""

import sqlalchemy as sa

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

DETAILS_SOURCES = ("zotero", "crossref", "openalex", "semantic_scholar", "arxiv", "search", "manual")


def upgrade() -> None:
    op.alter_column("papers", "file_path", existing_type=sa.Text(), nullable=True)
    op.add_column("papers", sa.Column("details_source", sa.Text(), nullable=True))
    values = ", ".join(f"'{v}'" for v in DETAILS_SOURCES)
    op.create_check_constraint("papers_details_source_check", "papers", f"details_source IN ({values})")


def downgrade() -> None:
    # ponytail: refuse rather than invent files
    if op.get_bind().execute(sa.text("SELECT 1 FROM papers WHERE file_path IS NULL LIMIT 1")).first():
        raise RuntimeError("papers without a PDF exist; delete them first")
    op.drop_constraint("papers_details_source_check", "papers")
    op.drop_column("papers", "details_source")
    op.alter_column("papers", "file_path", existing_type=sa.Text(), nullable=False)
