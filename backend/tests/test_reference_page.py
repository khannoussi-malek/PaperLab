"""To read, the one in-library match, and the References page's data (M21, D121, D164–D166, D177)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select, text

from app.core import references
from app.core.errors import NotFound
from app.models import ExternalRef, Note, NoteEmbedding, Paper, paper_references

# Every test here hides the owner's rows (below), as the other references tests do: one worker for all of them.
pytestmark = [pytest.mark.anyio, pytest.mark.xdist_group("references")]

RUN = uuid.uuid4().hex[:8]  # unique DOIs, OpenAlex IDs and workspace names per run (D37)
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)  # the test transaction freezes now(): To read times are set by hand


@pytest.fixture
async def library(session):
    """The dev database (D15) holds the owner's papers, references, note vectors and notes: hide them in this test's
    rolled-back transaction, so every count is the test's own."""
    for model in (paper_references, NoteEmbedding, ExternalRef, Note, Paper):
        await session.execute(delete(model))
    return session


async def add_papers(session, *titles: str, **fields) -> list[Paper]:
    added = [Paper(**{"file_path": "/nonexistent.pdf", "title": title, **fields}) for title in titles]
    session.add_all(added)
    await session.flush()
    return added


async def add_ref(session, title: str, **fields) -> ExternalRef:
    ref = ExternalRef(title=title, **fields)
    session.add(ref)
    await session.flush()
    return ref


async def link(session, ref: ExternalRef, *linked: Paper, direction: str = "cites") -> None:
    await session.execute(
        paper_references.insert(),
        [{"paper_id": paper.id, "ref_id": ref.id, "direction": direction, "position": 0} for paper in linked],
    )


def titles(rows) -> list[str]:
    return [row.title for row in rows]


async def queued(session, ref_id) -> datetime | None:
    return await session.scalar(select(ExternalRef.queued_at).where(ExternalRef.id == ref_id))


# --- To read (D164) ----------------------------------------------------------------------------------------------


async def test_queue_marks_a_reference_once_and_unqueue_clears_it(library):
    ref = await add_ref(library, "To read later")

    assert await references.queue(library, ref.id) is not None
    await library.execute(text("UPDATE external_refs SET queued_at = :at WHERE id = :id"), {"at": T0, "id": ref.id})
    assert await references.queue(library, ref.id) == T0  # a second To read keeps the first time

    await references.unqueue(library, ref.id)
    await references.unqueue(library, ref.id)  # and a second unmark is harmless
    assert await queued(library, ref.id) is None


async def test_an_unknown_reference_can_be_neither_queued_nor_unqueued(library):
    for call in (references.queue, references.unqueue):
        with pytest.raises(NotFound):
            await call(library, uuid.uuid4())
