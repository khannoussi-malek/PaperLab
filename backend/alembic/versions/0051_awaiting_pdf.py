"""A search hit can await its PDF: acquisition_status 'awaiting_pdf', a hit linked to a paper saved without one.

Revision ID: 0051
Revises: 0050
"""

import sqlalchemy as sa

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

STATUSES = ("not_attempted", "queued", "imported", "failed", "manual")
OLD_NAME = "workspace_search_hits_acquisition_status_check"  # 0013's inline CHECK, named by Postgres
NAME = "ck_workspace_search_hits_acquisition_status"


def _check(name: str, statuses: tuple[str, ...]) -> None:
    values = ", ".join(f"'{v}'" for v in statuses)
    op.create_check_constraint(name, "workspace_search_hits", f"acquisition_status IN ({values})")


def upgrade() -> None:
    op.drop_constraint(OLD_NAME, "workspace_search_hits", type_="check")
    _check(NAME, (*STATUSES, "awaiting_pdf"))


def downgrade() -> None:
    # ponytail: refuse rather than guess which state each hit was in
    hits = sa.text("SELECT 1 FROM workspace_search_hits WHERE acquisition_status = 'awaiting_pdf' LIMIT 1")
    if op.get_bind().execute(hits).first():
        raise RuntimeError("hits awaiting a PDF exist; set them back to failed first")
    op.drop_constraint(NAME, "workspace_search_hits", type_="check")
    _check(OLD_NAME, STATUSES)
