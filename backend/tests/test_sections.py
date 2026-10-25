"""Sections and the reader's role fixes (M16 spec §3.1, §4.2), on real Postgres in a rolled-back transaction."""

import uuid

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from app.core import papers, sections
from app.core.chunking import ChunkDraft
from app.core.errors import InvalidInput, NotFound
from app.models import Chunk, LLMOutput, Paper, section_role_overrides

pytestmark = pytest.mark.anyio


async def paper_with_headings(
    session, headings: list[str | None], texts: list[str] | None = None, status: str = "ready", has_pdf: bool = True
) -> tuple[Paper, list[Chunk]]:
    """One chunk per entry of `headings`, in reading order: chunk i is on page i + 1, under headings[i]. Without a PDF
    the paper has no file and its chunks are on ABSTRACT_PAGE (0), like a saved-without-PDF paper's abstract."""
    paper = Paper(title="Sectioned paper", file_path="/nonexistent.pdf" if has_pdf else None, status=status)
    session.add(paper)
    await session.flush()
    chunks = [
        Chunk(
            paper_id=paper.id,
            ordinal=i,
            page=i + 1 if has_pdf else 0,
            bbox=[[72, 100, 540, 120]] if has_pdf else [],
            section_title=heading,
            text=texts[i] if texts else f"Text of chunk {i}.",
            embed_model="test",
            strategy_ver=1,
        )
        for i, heading in enumerate(headings)
    ]
    session.add_all(chunks)
    await session.commit()
    return paper, chunks


async def fixes_of(session, paper_id) -> list[tuple[str, str]]:
    table = section_role_overrides
    query = select(table.c.section_title, table.c.role).where(table.c.paper_id == paper_id)
    return [tuple(row) for row in (await session.execute(query)).all()]


async def test_sections_are_runs_of_one_heading_in_reading_order(session):
    headings = [None, "1 Introduction", "1 Introduction", "2 Related Work", "1 Introduction", "3 Method"]
    texts = ["Title page.", "x" * 200, "Second intro chunk.", "Prior work.", "Intro again.", "How it was done."]
    paper, chunks = await paper_with_headings(session, headings, texts)

    found = await sections.paper_sections(session, paper.id)

    assert [(s.title, s.role, s.source, s.chunk_ids) for s in found] == [
        (None, "other", "none", [chunks[0].id]),
        ("1 Introduction", "intro", "keyword", [chunks[1].id, chunks[2].id]),
        ("2 Related Work", "related", "keyword", [chunks[3].id]),
        ("1 Introduction", "intro", "keyword", [chunks[4].id]),
        ("3 Method", "method", "keyword", [chunks[5].id]),
    ]
    assert (found[1].first_chunk_id, found[1].page, found[1].preview) == (chunks[1].id, 2, "x" * 160)


async def test_a_fix_applies_to_every_section_with_that_heading(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction", "2 Method", "1 Introduction"])

    await sections.set_role(session, paper.id, "1 Introduction", "conclusion")

    found = await sections.paper_sections(session, paper.id)
    assert [(s.title, s.role, s.source) for s in found] == [
        ("1 Introduction", "conclusion", "user"),
        ("2 Method", "method", "keyword"),
        ("1 Introduction", "conclusion", "user"),
    ]


async def test_set_role_creates_updates_and_none_deletes_a_fix(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction", "2 Method"])

    await sections.set_role(session, paper.id, "2 Method", "results")
    await sections.set_role(session, paper.id, "2 Method", "conclusion")
    fixed = await sections.paper_sections(session, paper.id)
    stored = await fixes_of(session, paper.id)
    await sections.set_role(session, paper.id, "2 Method", None)
    automatic = await sections.paper_sections(session, paper.id)

    assert (fixed[1].role, fixed[1].source) == ("conclusion", "user")
    assert stored == [("2 Method", "conclusion")]
    assert (automatic[1].role, automatic[1].source) == ("method", "keyword")
    assert await fixes_of(session, paper.id) == []


async def test_set_role_refuses_an_unknown_heading_or_paper(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction"])

    with pytest.raises(InvalidInput, match="unknown_section"):
        await sections.set_role(session, paper.id, "9 Appendix", "back")
    with pytest.raises(NotFound):
        await sections.set_role(session, uuid.uuid4(), "1 Introduction", "intro")
    with pytest.raises(NotFound):
        await sections.paper_sections(session, uuid.uuid4())


async def test_a_fix_survives_a_re_ingest(session):
    paper, chunks = await paper_with_headings(session, ["1 Introduction", "2 Method"])
    drafts = [ChunkDraft(c.ordinal, c.page, c.bbox, c.section_title, c.text) for c in chunks]
    await sections.set_role(session, paper.id, "2 Method", "conclusion")

    await papers.replace_chunks(session, paper.id, drafts)

    found = await sections.paper_sections(session, paper.id)
    assert found[1].chunk_ids != [chunks[1].id]  # new chunks, same heading
    assert (found[1].title, found[1].role, found[1].source) == ("2 Method", "conclusion", "user")


async def test_deleting_the_paper_deletes_its_fixes(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction"])
    await sections.set_role(session, paper.id, "1 Introduction", "abstract")

    await papers.delete_paper(session, paper.id)

    table = section_role_overrides
    left = await session.scalar(select(func.count()).select_from(table).where(table.c.paper_id == paper.id))
    assert left == 0


async def test_the_role_check_refuses_an_unknown_role(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction"])
    row = {"paper_id": paper.id, "section_title": "1 Introduction", "role": "bogus"}

    with pytest.raises(IntegrityError, match="section_role_overrides_role_check"):
        await session.execute(insert(section_role_overrides).values(**row))


async def test_a_paper_without_a_pdf_has_no_sections_even_with_its_abstract_chunk(session):
    # R1: the lone ABSTRACT_PAGE chunk of a saved-without-PDF paper is not a section.
    paper, chunks = await paper_with_headings(session, ["Abstract"], has_pdf=False)

    found = await sections.paper_sections(session, paper.id)

    assert (len(chunks), chunks[0].page, found) == (1, 0, [])


async def test_an_output_reads_the_full_lens_unless_it_says_otherwise(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction"])
    output = LLMOutput(paper_id=paper.id, kind="chat", content="a", model="fake", prompt_version=1)
    session.add(output)
    await session.commit()

    await session.refresh(output)

    assert output.lens == "full"


async def test_a_repeated_heading_resolved_by_position_is_one_section_for_roles(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction", "Our system", "3 Method", "Our system"])

    found = await sections.paper_sections(session, paper.id)

    assert [(s.title, s.role, s.source) for s in found if s.title == "Our system"] == [
        ("Our system", "related", "position"),
        ("Our system", "related", "position"),
    ]


async def test_set_role_refuses_a_paper_without_a_pdf(session):
    paper, _ = await paper_with_headings(session, ["Abstract"], has_pdf=False)

    with pytest.raises(InvalidInput, match="unknown_section"):
        await sections.set_role(session, paper.id, "Abstract", "abstract")
