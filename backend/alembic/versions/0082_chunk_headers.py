"""chunks.header: the "<title> · <section>" a chunk was embedded under, read by the keyword index too (M8,
document-aware chunk headers). NULL = embedded before headers; the ingest worker re-embeds those papers when
search is local.

Revision ID: 0082
Revises: 0081
Create Date: 2026-11-23
"""

from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def _tsv(expression: str) -> None:
    # Dropping the column drops its GIN index; adding it back rewrites the table (about a minute for ~50k chunks).
    op.execute("ALTER TABLE chunks DROP COLUMN tsv")
    op.execute(f"ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS ({expression}) STORED")
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)")


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ADD COLUMN header text")
    _tsv("to_tsvector('english', spelling_us(coalesce(header || ' ', '') || text))")


def downgrade() -> None:
    _tsv("to_tsvector('english', spelling_us(text))")
    op.execute("ALTER TABLE chunks DROP COLUMN header")
