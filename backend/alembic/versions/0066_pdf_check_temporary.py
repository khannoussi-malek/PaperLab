"""A free-copy check can end "temporary": a source was busy or unreachable, so it says nothing about a copy.

Revision ID: 0066
Revises: 0065
"""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_papers_pdf_check_result", "papers")
    op.create_check_constraint(
        "ck_papers_pdf_check_result", "papers", "pdf_check_result IN ('found', 'none', 'temporary', 'error')"
    )


def downgrade() -> None:
    op.execute("UPDATE papers SET pdf_check_result = 'error' WHERE pdf_check_result = 'temporary'")
    op.drop_constraint("ck_papers_pdf_check_result", "papers")
    op.create_check_constraint("ck_papers_pdf_check_result", "papers", "pdf_check_result IN ('found', 'none', 'error')")
