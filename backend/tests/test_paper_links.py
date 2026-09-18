"""The links the owner draws between two papers: the one stored link kind (P6, D110)."""

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

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


async def test_a_pair_linked_between_the_check_and_the_insert_is_already_linked(session, monkeypatch):
    """A double submit: both requests pass the duplicate check before either inserts, so the second insert hits the
    unique index. It still reads "already linked", and the session stays usable."""
    left, right = await add_papers(session)
    # Read now: the rollback inside create() expires the object.
    link_id = (await paper_links.create(session, left.id, right.id, "builds on")).id
    real_scalar = session.scalar
    checks = []

    async def first_check_misses(*args, **kwargs):
        # The duplicate check ran before the other request's link was committed.
        checks.append(args)
        return None if len(checks) == 1 else await real_scalar(*args, **kwargs)

    monkeypatch.setattr(session, "scalar", first_check_misses)

    with pytest.raises(Conflict, match="already linked"):
        await paper_links.create(session, right.id, left.id, "builds on")
    assert await real_scalar(select(PaperLink.id).where(PaperLink.id == link_id)) == link_id


async def test_a_paper_deleted_between_the_check_and_the_insert_is_not_found(session, monkeypatch):
    left, right = await add_papers(session)
    real_get_paper = paper_links.get_paper
    deleted = []

    async def deleted_just_after_its_check(session, paper_id):
        paper = await real_get_paper(session, paper_id)
        if paper_id == right.id and not deleted:
            # Another request deletes the paper right after create() found it, before the insert.
            await session.execute(delete(Paper).where(Paper.id == right.id))
            await session.commit()
            deleted.append(paper_id)
        return paper

    monkeypatch.setattr(paper_links, "get_paper", deleted_just_after_its_check)

    with pytest.raises(NotFound):
        await paper_links.create(session, left.id, right.id, "builds on")


async def test_an_insert_refused_for_another_reason_is_not_reported_as_already_linked(session, monkeypatch):
    left, right = await add_papers(session)
    real_commit = session.commit
    commits = []

    async def first_commit_refused():
        commits.append(1)
        if len(commits) == 1:
            raise IntegrityError("INSERT INTO paper_links", {}, Exception("another constraint"))
        await real_commit()

    monkeypatch.setattr(session, "commit", first_commit_refused)

    with pytest.raises(IntegrityError):
        await paper_links.create(session, left.id, right.id, "builds on")
