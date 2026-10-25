"""AI briefs (M16 spec §4.2, D50): what a brief reads, how it is saved, and when it goes out of date."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from test_sections import paper_with_headings

from app.core import briefs, chat, papers, sections
from app.core.chunking import ChunkDraft
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.retrieval import RetrievedChunk
from app.models import LLMOutput

pytestmark = pytest.mark.anyio

HEADINGS = ["Abstract", "1 Introduction", "2 Method", "2 Method", "3 Results", "4 Conclusion"]
LONG_METHOD = (["1 Introduction", "2 Method", "2 Method", "2 Method"], ["Intro.", *["m" * 10_000] * 3])


def source(text: str) -> RetrievedChunk:
    return RetrievedChunk(id=uuid.uuid4(), paper_id=uuid.uuid4(), page=1, section=None, bbox=[], text=text)


async def brief_on(session, paper_id, lens, content="A brief [C1].", minutes_ago=0) -> uuid.UUID:
    """Prepares and saves a brief, written `minutes_ago` (the test transaction freezes now())."""
    prepared = await briefs.prepare_brief(session, paper_id, lens)
    output_id = await briefs.save_brief(session, paper_id, lens, prepared, content, "fake", "Fake")
    written = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    await session.execute(update(LLMOutput).where(LLMOutput.id == output_id).values(created_at=written))
    return output_id


def test_the_prompt_has_one_instruction_per_lens_but_full_paper():
    assert (
        sorted(briefs.LENS_INSTRUCTIONS) == sorted(briefs.BRIEFABLE) == ["critical", "key_ideas", "method", "related"]
    )
    assert "{lens_instruction}" in briefs.PROMPT_TEMPLATE and "{context}" in briefs.PROMPT_TEMPLATE


def test_cut_to_budget_keeps_whole_chunks_from_the_start():
    three = [source("a" * 10), source("b" * 10), source("c" * 10)]

    assert briefs.cut_to_budget(three, 20) == three[:2]
    assert briefs.cut_to_budget(three, 19) == three[:1]
    assert briefs.cut_to_budget(three, 30) == three
    assert briefs.cut_to_budget([], 30) == []
    assert briefs.cut_to_budget(three) == three  # SMALL_PAPER_CHARS


async def test_a_small_lens_goes_whole_in_reading_order(session):
    paper, chunks = await paper_with_headings(session, HEADINGS)

    prepared = await briefs.prepare_brief(session, paper.id, "key_ideas")

    assert [s.id for s in prepared.sources] == [chunks[i].id for i in (0, 1, 5)]
    assert prepared.whole_paper is True
    assert (prepared.system, prepared.prompt_version) == (briefs.SYSTEM_PROMPT, briefs.BRIEF_PROMPT_VERSION)
    assert prepared.prompt.startswith(briefs.LENS_INSTRUCTIONS["key_ideas"])
    assert "[C3] (Sectioned paper, p.6, 4 Conclusion)\nText of chunk 5." in prepared.prompt
    assert (prepared.notes, prepared.notes_total) == ([], None)


async def test_a_large_lens_is_cut_at_a_chunk_boundary_and_marked_partial(session):
    paper, chunks = await paper_with_headings(session, *LONG_METHOD)

    prepared = await briefs.prepare_brief(session, paper.id, "method")

    assert [s.id for s in prepared.sources] == [chunks[1].id, chunks[2].id]  # 20,000 of 30,000 characters
    assert prepared.whole_paper is False


async def test_a_brief_is_refused_for_full_paper_an_empty_lens_and_an_unready_or_unknown_paper(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    extracting, _ = await paper_with_headings(session, HEADINGS, status="extracting")

    for lens in ("full", "bogus"):
        with pytest.raises(InvalidInput, match="lens_not_briefable"):
            await briefs.prepare_brief(session, paper.id, lens)
    with pytest.raises(Conflict, match="lens_empty"):
        await briefs.prepare_brief(session, paper.id, "related")
    with pytest.raises(Conflict, match="paper_not_ready"):
        await briefs.prepare_brief(session, extracting.id, "key_ideas")
    with pytest.raises(NotFound):
        await briefs.prepare_brief(session, uuid.uuid4(), "key_ideas")


async def test_a_paper_without_a_pdf_needs_full_text_before_its_lens_is_called_empty(session):
    # R1: such a paper has no sections, so its lenses are empty; the useful answer is that it needs its PDF.
    paper, _ = await paper_with_headings(session, ["Abstract"], has_pdf=False)

    with pytest.raises(Conflict, match="needs_full_text"):
        await briefs.prepare_brief(session, paper.id, "key_ideas")


async def test_save_brief_stores_its_lens_passages_and_citations(session):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    prepared = await briefs.prepare_brief(session, paper.id, "key_ideas")

    output_id = await briefs.save_brief(
        session, paper.id, "key_ideas", prepared, "It claims X [C1] and Y [C3][C9].", "qwen3:8b", "Ollama"
    )

    output = await session.get(LLMOutput, output_id)
    assert (output.kind, output.lens, output.paper_id, output.question) == ("brief", "key_ideas", paper.id, None)
    assert output.source_chunks == [chunks[i].id for i in (0, 1, 5)]
    assert output.cited_chunks == [chunks[0].id, chunks[5].id]  # [C9] is no source
    assert (output.whole_paper, output.model, output.connection_name, output.prompt_version) == (
        True,
        "qwen3:8b",
        "Ollama",
        1,
    )


async def test_list_briefs_gives_the_newest_brief_per_lens(session):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    await brief_on(session, paper.id, "key_ideas", "Old [C1].", minutes_ago=5)
    newest = await brief_on(session, paper.id, "key_ideas", "New [C2].", minutes_ago=1)
    method = await brief_on(session, paper.id, "method", "Method [C1].", minutes_ago=3)

    listed = await briefs.list_briefs(session, paper.id)

    assert [(b.output.id, b.output.lens, b.stale) for b in listed] == [
        (newest, "key_ideas", False),
        (method, "method", False),
    ]
    assert [s.id for s in listed[0].sources] == [chunks[i].id for i in (0, 1, 5)]


async def test_a_brief_goes_stale_when_a_fix_changes_its_lens_and_not_otherwise(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    await brief_on(session, paper.id, "key_ideas")

    await sections.set_role(session, paper.id, "3 Results", "method")  # outside Key ideas before and after
    unrelated = await briefs.list_briefs(session, paper.id)
    await sections.set_role(session, paper.id, "2 Method", "conclusion")  # Key ideas gains both method chunks
    related = await briefs.list_briefs(session, paper.id)

    assert [b.stale for b in unrelated] == [False]
    assert [b.stale for b in related] == [True]


async def test_a_brief_goes_stale_when_a_re_ingest_replaces_its_chunks(session):
    paper, chunks = await paper_with_headings(session, HEADINGS)
    drafts = [ChunkDraft(c.ordinal, c.page, c.bbox, c.section_title, c.text) for c in chunks]
    await brief_on(session, paper.id, "key_ideas")

    await papers.replace_chunks(session, paper.id, drafts)

    [brief] = await briefs.list_briefs(session, paper.id)
    assert brief.stale is True
    assert brief.sources == [None, None, None]  # their markers now render as plain text


async def test_a_partial_brief_is_not_stale_just_because_it_was_cut(session):
    paper, _ = await paper_with_headings(session, *LONG_METHOD)
    await brief_on(session, paper.id, "method")

    [brief] = await briefs.list_briefs(session, paper.id)

    assert (brief.stale, brief.output.whole_paper) == (False, False)


async def test_an_unknown_paper_has_no_briefs_and_chat_history_never_lists_one(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    await brief_on(session, paper.id, "key_ideas")

    with pytest.raises(NotFound):
        await briefs.list_briefs(session, uuid.uuid4())
    assert await chat.list_answers(session, paper.id) == []
