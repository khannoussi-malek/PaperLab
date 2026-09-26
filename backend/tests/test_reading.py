"""The reader's own record of a paper: passes finished and their decision (M21, D118, D119, D163)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import ExternalRef, Paper

pytestmark = pytest.mark.anyio

RUN = uuid.uuid4().hex[:8]  # the owner's workspaces share the dev database (D37)


async def add_paper(session, **fields) -> Paper:
    paper = Paper(file_path="/nonexistent.pdf", **{"title": f"Reading {RUN}", **fields})
    session.add(paper)
    await session.commit()
    return paper


# --- the columns (D119, D120) ------------------------------------------------------------------------------------


async def test_a_new_paper_starts_unread_and_undecided_and_a_reference_unqueued(session):
    paper, ref = await add_paper(session), ExternalRef(title=f"A reference {RUN}")
    session.add(ref)
    await session.commit()
    await session.refresh(paper)
    await session.refresh(ref)

    assert (paper.reading_pass, paper.triage, ref.queued_at) == (0, None, None)


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("reading_pass", 4, "papers_reading_pass_range"),
        ("reading_pass", -1, "papers_reading_pass_range"),
        ("triage", "maybe", "papers_triage_value"),
    ],
)
async def test_the_database_refuses_a_level_or_a_decision_it_does_not_know(session, column, value, constraint):
    paper = await add_paper(session)

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(
            text(f"UPDATE papers SET {column} = :value WHERE id = :id"), {"value": value, "id": paper.id}
        )
    await session.rollback()
