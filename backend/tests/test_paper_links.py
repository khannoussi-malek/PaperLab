"""The links the owner draws between two papers: the one stored link kind (P6, D110)."""

import uuid

import pytest
from sqlalchemy import delete, select

from app.core import paper_links
from app.core.errors import Conflict, InvalidInput, NotFound
from app.models import Paper, PaperLink

pytestmark = pytest.mark.anyio


async def add_papers(session, count: int = 2) -> list[Paper]:
    papers = [Paper(title=f"Link {n} {uuid.uuid4().hex[:8]}", file_path="/nonexistent.pdf") for n in range(count)]
    session.add_all(papers)
    await session.commit()
    return papers


async def test_create_edit_and_delete_a_link(session):
    left, right = await add_papers(session)

    link = await paper_links.create(session, left.id, right.id, "  builds on  ")
    assert (link.from_paper, link.to_paper, link.label) == (left.id, right.id, "builds on")

    renamed = await paper_links.set_label(session, link.id, " contradicts ")
    assert (renamed.id, renamed.from_paper, renamed.to_paper, renamed.label) == (
        link.id,
        left.id,
        right.id,
        "contradicts",
    )

    await paper_links.remove(session, link.id)
    assert await session.scalar(select(PaperLink.id).where(PaperLink.id == link.id)) is None
    for gone in (paper_links.set_label(session, link.id, "again"), paper_links.remove(session, link.id)):
        with pytest.raises(NotFound):
            await gone


async def test_a_pair_is_linked_once_whichever_way_round_it_is_drawn(session):
    left, right = await add_papers(session)
    await paper_links.create(session, left.id, right.id, "builds on")

    for pair in ((left.id, right.id), (right.id, left.id)):
        with pytest.raises(Conflict, match="already linked"):
            await paper_links.create(session, *pair, "builds on")


async def test_an_unknown_paper_and_a_paper_linked_to_itself_are_refused(session):
    (paper,) = await add_papers(session, 1)

    with pytest.raises(InvalidInput, match="two different papers"):
        await paper_links.create(session, paper.id, paper.id, "itself")
    for pair in ((paper.id, uuid.uuid4()), (uuid.uuid4(), paper.id)):
        with pytest.raises(NotFound):
            await paper_links.create(session, *pair, "builds on")


async def test_a_label_is_trimmed_and_must_be_one_to_eighty_characters(session):
    left, right = await add_papers(session)

    for blank in ("", "   ", "\n\t"):
        with pytest.raises(InvalidInput, match="short label"):
            await paper_links.create(session, left.id, right.id, blank)
    with pytest.raises(InvalidInput, match="under 80"):
        await paper_links.create(session, left.id, right.id, "x" * 81)

    link = await paper_links.create(session, left.id, right.id, "x" * 80)
    assert len(link.label) == 80
    with pytest.raises(InvalidInput, match="under 80"):
        await paper_links.set_label(session, link.id, "y" * 81)


async def test_deleting_a_paper_removes_its_links(session):
    left, right = await add_papers(session)
    link = await paper_links.create(session, left.id, right.id, "builds on")

    await session.execute(delete(Paper).where(Paper.id == left.id))
    await session.commit()

    assert await session.scalar(select(PaperLink.id).where(PaperLink.id == link.id)) is None


async def test_a_race_condition_on_double_submit_raises_conflict(session, monkeypatch):
    """When two concurrent requests bypass the pre-check and both try to insert, the second's commit raises
    IntegrityError on the unique index. The exception handler must catch it, roll back, and raise Conflict."""
    left, right = await add_papers(session)

    # Insert a link manually to set up the race condition state.
    link = PaperLink(from_paper=left.id, to_paper=right.id, label="builds on")
    session.add(link)
    await session.commit()
    link_id = link.id  # Store the ID before any potential expiry

    # Monkeypatch the select call in paper_links to return a query that will always return None,
    # simulating a race where the pre-check is bypassed.
    original_select = paper_links.select

    def mock_select(*args, **kwargs):
        # Return a query that when scalar()'d will return None
        return select(None).select_from(PaperLink).where(False)

    monkeypatch.setattr("app.core.paper_links.select", mock_select)

    # Now call create() for the same pair the other way round. The pre-check will return None,
    # but the commit will fail on IntegrityError, which should be caught and re-raised as Conflict.
    with pytest.raises(Conflict, match=paper_links.ALREADY_LINKED):
        await paper_links.create(session, right.id, left.id, "builds on")

    # Verify the session is still usable after the rollback and the original link is still there.
    result = await session.scalar(original_select(PaperLink.id).where(PaperLink.id == link_id))
    assert result is not None
