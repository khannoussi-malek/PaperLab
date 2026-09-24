"""The search source setting (D151): one row, read per question and per job, its keys kept in model connections."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import EmbeddingSource

pytestmark = pytest.mark.anyio


async def test_every_test_starts_on_built_in_whatever_the_owner_chose(session):
    """D159: the dev database (D15) holds the owner's choice. Each test's session sees an empty table of the same shape
    in its own temporary schema instead, so no test reads the owner's source, and none waits on its row's lock."""
    schema = await session.scalar(
        text("SELECT relnamespace::regnamespace::text FROM pg_class WHERE oid = 'embedding_source'::regclass")
    )

    assert schema.startswith("pg_temp")
    assert await session.scalar(select(func.count()).select_from(EmbeddingSource)) == 0
    with pytest.raises(IntegrityError):  # the shadow keeps the table's rules: no Ollama source without a connection
        async with session.begin_nested():
            session.add(EmbeddingSource(kind="ollama", model="nomic-embed-text"))
