"""Lenses (M16 spec §2): which chunks each lens reads, pure on (chunk, role) pairs and through the service."""

import uuid

import pytest
from test_sections import paper_with_headings

from app.core import lenses, sections
from app.core.errors import InvalidInput, NotFound
from app.core.lenses import LENSES, POSITION_CHUNKS, LensChunks, pick

pytestmark = pytest.mark.anyio


def ordered(*roles: str) -> list[tuple[uuid.UUID, str]]:
    return [(uuid.uuid4(), role) for role in roles]


def test_no_chunks_give_an_empty_lens_and_no_positional_fallback():
    # R1: a paper without a PDF has no sections; Key ideas must not claim to show "the start and end" of nothing.
    assert pick([], LENSES["key_ideas"]) == LensChunks([], False, ["abstract", "intro", "conclusion"])
    assert pick([], LENSES["full"]) == LensChunks([], False, [])


def ids_of(pairs, *indices) -> list[uuid.UUID]:
    return [pairs[i][0] for i in indices]


def test_full_paper_is_every_chunk():
    pairs = ordered("other", "intro", "back")

    assert pick(pairs, LENSES["full"]) == LensChunks(ids_of(pairs, 0, 1, 2), False, [])


def test_each_lens_reads_its_roles_in_reading_order():
    pairs = ordered("other", "abstract", "intro", "related", "method", "results", "results", "conclusion", "back")

    assert pick(pairs, LENSES["key_ideas"]) == LensChunks(ids_of(pairs, 1, 2, 7), False, [])
    assert pick(pairs, LENSES["critical"]) == LensChunks(ids_of(pairs, 4, 5, 6), False, ["limitations"])
    assert pick(pairs, LENSES["method"]) == LensChunks(ids_of(pairs, 4), False, [])
    assert pick(pairs, LENSES["related"]) == LensChunks(ids_of(pairs, 3), False, [])


def test_key_ideas_reads_the_discussion_when_there_is_no_conclusion():
    pairs = ordered("abstract", "intro", "method", "discussion", "back")

    assert pick(pairs, LENSES["key_ideas"]) == LensChunks(ids_of(pairs, 0, 1, 3), False, ["conclusion"])


def test_key_ideas_with_an_introduction_only_is_the_introduction():
    pairs = ordered("intro", "method")

    assert pick(pairs, LENSES["key_ideas"]) == LensChunks(ids_of(pairs, 0), False, ["abstract", "conclusion"])


def test_key_ideas_falls_back_to_the_first_and_last_body_chunks():
    pairs = ordered("other", "other", "abstract", "other", "other", "other", "other", "other", "other", "back", "back")

    found = pick(pairs, LENSES["key_ideas"])

    assert POSITION_CHUNKS == 3
    assert found == LensChunks(ids_of(pairs, 0, 1, 2, 6, 7, 8), True, ["intro", "conclusion"])


def test_a_short_paper_falls_back_to_its_whole_body_once():
    pairs = ordered("other", "other", "other", "other", "back")

    found = pick(pairs, LENSES["key_ideas"])

    assert found == LensChunks(ids_of(pairs, 0, 1, 2, 3), True, ["abstract", "intro", "conclusion"])


def test_a_paper_of_back_matter_only_announces_no_fallback():
    # the banner "Showing the start and end of the paper" never sits over nothing
    found = pick(ordered("back", "back"), LENSES["key_ideas"])

    assert found == LensChunks([], False, ["abstract", "intro", "conclusion"])


def test_a_discussion_without_an_introduction_is_no_fallback():
    pairs = ordered("abstract", "method", "discussion")

    found = pick(pairs, LENSES["key_ideas"])

    assert found == LensChunks(ids_of(pairs, 0, 2), False, ["intro", "conclusion"])


def test_a_lens_with_no_sections_is_empty_and_names_what_is_missing():
    pairs = ordered("intro", "method", "results", "conclusion")

    assert pick(pairs, LENSES["related"]) == LensChunks([], False, ["related"])


async def test_lens_chunks_follow_the_papers_headings_and_the_readers_fixes(session):
    paper, chunks = await paper_with_headings(session, ["1 Introduction", "2 Method"])

    before = await lenses.lens_chunks(session, paper.id, "key_ideas")
    await sections.set_role(session, paper.id, "2 Method", "conclusion")
    after = await lenses.lens_chunks(session, paper.id, "key_ideas")

    assert before == LensChunks([chunks[0].id], False, ["abstract", "conclusion"])
    assert after == LensChunks([chunks[0].id, chunks[1].id], False, ["abstract"])


async def test_lens_chunks_refuse_an_unknown_lens_or_paper(session):
    paper, _ = await paper_with_headings(session, ["1 Introduction"])

    with pytest.raises(InvalidInput, match="unknown_lens"):
        await lenses.lens_chunks(session, paper.id, "bogus")
    with pytest.raises(NotFound):
        await lenses.lens_chunks(session, uuid.uuid4(), "key_ideas")


async def test_paper_lenses_gives_the_sections_and_every_lens_in_order(session):
    headings = ["Abstract", "1 Introduction", "2 Method", "3 Results", "References"]
    paper, chunks = await paper_with_headings(session, headings)

    found, picked = await lenses.paper_lenses(session, paper.id)

    assert [s.title for s in found] == headings
    assert [(lens.id, lens.label) for lens, _ in picked] == [
        ("full", "Full paper"),
        ("key_ideas", "Key ideas"),
        ("critical", "Critical check"),
        ("method", "How they did it"),
        ("related", "Related work"),
    ]
    critical = dict((lens.id, chosen) for lens, chosen in picked)["critical"]
    assert critical == LensChunks([chunks[2].id, chunks[3].id], False, ["limitations"])


async def test_a_paper_without_a_pdf_has_empty_lenses(session):
    paper, _ = await paper_with_headings(session, ["Abstract"], has_pdf=False)

    found, picked = await lenses.paper_lenses(session, paper.id)

    assert found == []
    assert all(chosen.chunk_ids == [] and not chosen.positional_fallback for _, chosen in picked)
    assert (await lenses.lens_chunks(session, paper.id, "key_ideas")).chunk_ids == []
