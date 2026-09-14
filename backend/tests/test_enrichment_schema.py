import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from app.core import papers
from app.models import Author, Paper, paper_authors, paper_topics

pytestmark = pytest.mark.anyio


async def add_paper(session, **fields) -> Paper:
    paper = Paper(title="enriched paper", file_path="/nonexistent.pdf", **fields)
    session.add(paper)
    await session.commit()
    return paper


async def test_enrichment_columns_default_to_unknown(session):
    paper = await add_paper(session)
    await session.refresh(paper)

    assert (paper.is_retracted, paper.manual_fields, paper.authors) == (False, [], [])
    assert (paper.type, paper.oa_status, paper.oa_url, paper.issn) == (None, None, None, None)
    assert (paper.cited_by_count, paper.referenced_works_count) == (None, None)


async def test_deleting_a_paper_removes_its_authorships_and_topics_but_keeps_the_authors(session):
    paper = await add_paper(session)
    author = Author(openalex_id="A0000000001", display_name="Schema Test Author")
    session.add(author)
    await session.flush()
    await session.execute(insert(paper_authors).values(paper_id=paper.id, author_id=author.id, position=1))
    await session.execute(insert(paper_topics).values(paper_id=paper.id, source="openalex", label="NLP", score=0.9))
    await session.commit()

    await papers.delete_paper(session, paper.id)

    links = select(func.count()).select_from(paper_authors).where(paper_authors.c.author_id == author.id)
    topics = select(func.count()).select_from(paper_topics).where(paper_topics.c.paper_id == paper.id)
    assert (await session.scalar(links), await session.scalar(topics)) == (0, 0)
    assert await session.get(Author, author.id) is not None


async def test_a_topic_source_is_author_openalex_or_venue(session):
    paper = await add_paper(session)

    with pytest.raises(IntegrityError, match="paper_topics_source_check"):
        await session.execute(insert(paper_topics).values(paper_id=paper.id, source="llm", label="guess"))
