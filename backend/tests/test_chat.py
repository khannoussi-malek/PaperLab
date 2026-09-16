import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import unit_vector
from sqlalchemy import delete, func, select
from test_chat_workspace import NOW, add_note

from app.core import chat, prompts
from app.core.errors import Conflict, NotFound
from app.core.retrieval import RetrievedChunk
from app.models import Chunk, LLMOutput, Note, Paper

pytestmark = pytest.mark.anyio


async def make_paper(session, texts: list[str], *, status="ready", embedded=True, **fields) -> Paper:
    paper = Paper(title="Attention Is All You Need", file_path="/nonexistent.pdf", status=status, **fields)
    session.add(paper)
    await session.flush()
    session.add_all(
        Chunk(
            paper_id=paper.id,
            ordinal=i,
            page=i + 1,
            bbox=[[72, 100 + i, 300, 120 + i]],
            section_title="Method" if i % 2 else None,
            text=text,
            embedding=unit_vector(text) if embedded else None,
            embed_model="test",
            strategy_ver=1,
        )
        for i, text in enumerate(texts)
    )
    await session.commit()
    return paper


async def chunks_of(session, paper_id) -> list[Chunk]:
    return list(await session.scalars(select(Chunk).where(Chunk.paper_id == paper_id).order_by(Chunk.ordinal)))


def source(page=4, section="Method", text="Self-attention relates positions.") -> RetrievedChunk:
    return RetrievedChunk(id=uuid.uuid4(), paper_id=uuid.uuid4(), page=page, section=section, bbox=[], text=text)


async def test_small_paper_skips_retrieval_and_sends_every_chunk_in_reading_order(session, embedder):
    texts = ["Intro paragraph.", "Method paragraph.", "Results paragraph."]
    paper = await make_paper(session, texts)

    prepared = await chat.prepare(session, paper.id, "What is the method?", embedder)

    assert prepared.whole_paper is True
    assert [s.text for s in prepared.sources] == texts
    assert embedder.calls == []
    assert prepared.system == chat.SYSTEM_PROMPT
    assert "[C3] (Attention Is All You Need, p.3)\nResults paragraph." in prepared.prompt
    assert prepared.prompt.rstrip().endswith("Question: What is the method?")


async def test_large_paper_sends_the_8_nearest_chunks(session, embedder):
    texts = [f"chunk {i} " + "x" * 2_100 for i in range(12)]  # 12 x ~2,108 chars > SMALL_PAPER_CHARS
    paper = await make_paper(session, texts)
    embedder.vectors["search_query: Which chunk?"] = unit_vector(texts[5])

    prepared = await chat.prepare(session, paper.id, "Which chunk?", embedder)

    assert prepared.whole_paper is False
    assert len(prepared.sources) == 8
    assert prepared.sources[0].text == texts[5]
    assert embedder.calls[0][0] == ["search_query: Which chunk?"]
    assert "[C8]" in prepared.prompt and "[C9]" not in prepared.prompt


def test_context_names_author_year_page_and_section():
    paper = Paper(title="BERT", authors=["Jacob Devlin"], year=2019)

    context = chat.format_context(paper, [source(), source(page=5, section=None, text="Second.")])

    assert context == (
        "[C1] (Devlin 2019, p.4, Method)\nSelf-attention relates positions.\n\n[C2] (Devlin 2019, p.5)\nSecond."
    )


def test_context_falls_back_to_the_title_without_an_author():
    assert chat.format_context(Paper(title="BERT", authors=[], year=2019), [source()]).startswith("[C1] (BERT, p.4,")


@pytest.mark.parametrize(
    ("authors", "year", "label"),
    [
        (["Jacob Devlin"], None, "Devlin"),  # K9: a missing year no longer drops the author
        (["   ", "Ming-Wei Chang"], 2019, "Chang 2019"),  # K9: a blank name used to raise IndexError
        (["  "], 2019, "BERT"),
    ],
)
def test_source_label_uses_whatever_is_known(authors, year, label):
    assert chat.source_label(Paper(title="BERT", authors=authors, year=year)) == label


def test_prompt_loader_reads_by_name_and_version(tmp_path, monkeypatch):
    assert "{context}" in prompts.load("chat", 1)

    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    (tmp_path / "summary.v2.md").write_text("version two")
    assert prompts.load("summary", 2) == "version two"
    with pytest.raises(FileNotFoundError, match=r"summary\.v3\.md"):
        prompts.load("summary", 3)


def test_parse_citations_keeps_known_sources_in_first_seen_order():
    text = "[C2] says so [C1][C3]; again [C2]. Not [C9], [C0] or C1."

    assert chat.parse_citations(text, 3) == [2, 1, 3]
    assert chat.parse_citations("no markers", 3) == []


async def test_save_answer_fills_every_column_and_inserts_no_note(session):
    paper = await make_paper(session, ["one", "two", "three"])
    notes_before = await session.scalar(select(func.count()).select_from(Note))
    prepared = await chat.prepare(session, paper.id, "why?")

    answer = "Because [C3] and [C1][C3]."

    output_id = await chat.save_answer(session, paper.id, "why?", prepared, answer, "qwen3:8b", "Ollama")

    row = await session.get(LLMOutput, output_id)
    ids = [s.id for s in prepared.sources]
    assert (row.paper_id, row.kind, row.question, row.content) == (paper.id, "chat", "why?", answer)
    assert (row.source_chunks, row.cited_chunks) == (ids, [ids[2], ids[0]])
    assert (row.model, row.prompt_version, row.whole_paper) == ("qwen3:8b", 2, True)
    assert await session.scalar(select(func.count()).select_from(Note)) == notes_before


async def test_prepare_gives_a_paper_its_own_notes_newest_first_after_the_passages(session):
    paper = await make_paper(session, ["one", "two"], authors=["Jacob Devlin"], year=2019)
    other = await make_paper(session, ["elsewhere"])
    older = await add_note(session, paper, "Masked LM.", page=2, updated_at=NOW - timedelta(days=1))
    newer = await add_note(session, paper, "Uses NSP.", provenance="llm")
    await add_note(session, other, "Not this paper.")

    prepared = await chat.prepare(session, paper.id, "What do my notes say?")

    assert (prepared.system, prepared.prompt_version) == (chat.SYSTEM_PROMPT, 2)
    assert "[N1]" in prepared.system
    notes_block = '[N1] (AI · Devlin 2019 p.1) "quote Uses NSP." — Uses NSP.\n[N2] (You · Devlin 2019 p.2)'
    assert notes_block in prepared.prompt and "Not this paper" not in prepared.prompt
    assert [n.id for n in prepared.notes] == [newer.id, older.id]
    assert (prepared.notes_used, prepared.notes_total) == (2, 2)
    order = [prepared.prompt.index(part) for part in ("[C1]", notes_block, "Question: What do my notes say?")]
    assert order == sorted(order)


async def test_prepare_on_a_paper_without_notes_says_so(session):
    paper = await make_paper(session, ["one"])

    prepared = await chat.prepare(session, paper.id, "why?")

    assert "Notes (newest first):\n\n(none)\n\nQuestion: why?" in prepared.prompt  # no earlier-questions block
    assert (prepared.notes, prepared.notes_used, prepared.notes_total) == ([], 0, 0)


def test_follow_up_sources_keep_every_fresh_passage_and_the_best_earlier_ones_that_fit():
    earlier = [source(text=f"earlier {i}") for i in range(8)]  # best match first
    fresh = [earlier[0], *(source(text=f"fresh {i}") for i in range(7))]  # the best earlier passage matches again

    # 12 places: 7 fresh-only passages, the shared one, and the 4 best earlier ones. Earlier passages come first.
    assert chat.follow_up_sources(earlier, fresh, limit=12) == earlier[:5] + fresh[1:]
    assert chat.follow_up_sources(earlier, [earlier[7], fresh[1]], limit=3) == [earlier[0], earlier[7], fresh[1]]
    assert chat.follow_up_sources([], fresh) == fresh


async def test_follow_up_asks_with_the_earlier_questions_and_their_passages_first(session, embedder):
    run = uuid.uuid4().hex  # unique vectors: dead HNSW entries from earlier runs never crowd this query
    texts = [f"{run} part {i} " + "x" * 3_000 for i in range(10)]  # over SMALL_PAPER_CHARS, so it retrieves
    paper = await make_paper(session, texts)
    chunks = await chunks_of(session, paper.id)
    embedder.vectors["search_query: And its cause?"] = unit_vector(texts[4])
    replaced = uuid.uuid4()  # a passage a re-ingest has since removed
    thread = chat.Thread(questions=["What is S1?", "Is it common?"], source_ids=[chunks[7].id, replaced, chunks[2].id])

    prepared = await chat.prepare(session, paper.id, "And its cause?", embedder, thread=thread)

    ids = [s.id for s in prepared.sources]
    assert ids[:3] == [chunks[7].id, chunks[2].id, chunks[4].id]
    assert len(ids) == len(set(ids)) <= chat.FOLLOW_UP_SOURCES and not prepared.whole_paper
    earlier = "Earlier questions in this conversation, oldest first:\n- What is S1?\n- Is it common?\n\n"
    assert prepared.prompt.endswith(earlier + "Question: And its cause?\n")


async def test_a_follow_up_on_a_small_paper_still_reads_it_whole(session):
    paper = await make_paper(session, ["one", "two"])
    thread = chat.Thread(questions=["What first?"], source_ids=[uuid.uuid4()])

    prepared = await chat.prepare(session, paper.id, "And then?", thread=thread)

    assert prepared.whole_paper and [s.text for s in prepared.sources] == ["one", "two"]
    assert "- What first?\n\nQuestion: And then?" in prepared.prompt


async def test_follow_ups_are_paper_chat_only_for_now(session):
    workspace = chat.Scope(workspace_id=uuid.uuid4())
    with pytest.raises(ValueError, match="paper chat"):
        await chat.prepare(session, workspace, "q", thread=chat.Thread(questions=["p"], source_ids=[]))


async def test_list_answers_oldest_first_with_replaced_chunks_as_none(session):
    paper = await make_paper(session, ["one", "two", "three"])
    chunks = await chunks_of(session, paper.id)
    now = datetime.now(timezone.utc)
    common = {"paper_id": paper.id, "kind": "chat", "content": "an answer", "model": "m", "prompt_version": 1}
    # Explicit timestamps: inside one test transaction now() never moves.
    newer = LLMOutput(**common, question="second", source_chunks=[chunks[2].id], created_at=now)
    older = LLMOutput(
        **common, question="first", source_chunks=[c.id for c in chunks[:2]], created_at=now - timedelta(minutes=1)
    )
    session.add_all([newer, older])
    await session.commit()
    await session.execute(delete(Chunk).where(Chunk.id == chunks[1].id))  # as a re-ingest would

    answers = await chat.list_answers(session, paper.id)

    assert [a.output.question for a in answers] == ["first", "second"]
    first_sources = answers[0].sources
    assert (first_sources[0].id, first_sources[0].page, first_sources[1]) == (chunks[0].id, 1, None)
    assert [s.id for s in answers[1].sources] == [chunks[2].id]
    with pytest.raises(NotFound):
        await chat.list_answers(session, uuid.uuid4())


async def test_prepare_rejects_unready_unindexed_and_unknown_papers(session, embedder):
    extracting = await make_paper(session, ["one"], status="extracting")
    large_unindexed = await make_paper(session, ["x" * 25_000], embedded=False)
    small_unindexed = await make_paper(session, ["one"], embedded=False)

    with pytest.raises(Conflict, match="^paper_not_ready$"):
        await chat.prepare(session, extracting.id, "q", embedder)
    with pytest.raises(Conflict, match="^paper_not_indexed$"):
        await chat.prepare(session, large_unindexed.id, "q", embedder)
    with pytest.raises(NotFound):
        await chat.prepare(session, uuid.uuid4(), "q", embedder)
    # A small paper is sent whole, so it needs no vectors.
    assert (await chat.prepare(session, small_unindexed.id, "q", embedder)).whole_paper is True
