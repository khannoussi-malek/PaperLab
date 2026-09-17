"""paper sources: which sources Find papers and Similar ask, their API keys and the contact email

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-17
"""

from alembic import op

# M17 (skills) was planned as 0009 and M16 (lenses) as 0010; they move to 0010 and 0011 (D71). If another branch still
# adds a 0009, whichever merges second renumbers revision and down_revision, after running `alembic downgrade 0008` on
# its own database: a database stamped with the other branch's 0009 would skip this migration without an error.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UPGRADE = [
    # One row: the primary key can only be true. Seeded by the API at startup from .env, only when missing (D74).
    # Keys are plain text, the same exposure as .env and llm_connections; no route returns them.
    """
    CREATE TABLE paper_sources (
      id                       boolean PRIMARY KEY DEFAULT true CHECK (id),
      contact_email            text CHECK (length(contact_email) <= 254),
      openalex_enabled         boolean NOT NULL DEFAULT false,
      crossref_enabled         boolean NOT NULL DEFAULT true,
      semantic_scholar_enabled boolean NOT NULL DEFAULT true,
      arxiv_enabled            boolean NOT NULL DEFAULT true,
      core_enabled             boolean NOT NULL DEFAULT true,
      unpaywall_enabled        boolean NOT NULL DEFAULT true,
      openalex_api_key         text,
      semantic_scholar_api_key text,
      core_api_key             text,
      updated_at               timestamptz NOT NULL DEFAULT now()
    )
    """,
]

DOWNGRADE = [
    "DROP TABLE paper_sources",
]


def upgrade() -> None:
    # One statement per execute: asyncpg prepares each one.
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
