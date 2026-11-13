"""M33: an answer keeps a copy of the passages it cited (llm_outputs.source_snapshot), written with the answer."""

import uuid

import pytest
from sqlalchemy import select, update
from test_chat import chunks_of, make_paper
from test_sections import paper_with_headings

from app.core import answer_provenance, briefs, chat, papers
from app.core.chunking import ChunkDraft
from app.core.errors import NotFound
from app.core.retrieval import RetrievedChunk
from app.models import LLMOutput, Note, Paper, Provenance

pytestmark = pytest.mark.anyio

HEADINGS = ["Abstract", "1 Introduction", "2 Method", "2 Method", "3 Results", "4 Conclusion"]
PAPER_ID = uuid.uuid4()


def passage(n: int, text: str = "passage") -> RetrievedChunk:
    """The n-th source of an answer (C{n}), on page n."""
    return RetrievedChunk(id=uuid.uuid4(), paper_id=PAPER_ID, page=n, section="Method", bbox=[], text=text)


def test_snapshot_keeps_the_cited_passages_in_label_order():
    chunks = [passage(n) for n in range(1, 6)]

    snap = answer_provenance.snapshot(chunks, ["C4", "C2", "C4"])

    assert [entry["label"] for entry in snap] == ["C2", "C4"]
    assert snap[0] == {
        "label": "C2",
        "paper_id": str(PAPER_ID),
        "page": 2,
        "section": "Method",
        "text": "passage",
        "from_abstract": False,
    }


def test_snapshot_stores_at_most_30_passages_and_cuts_each_text_at_2000_characters():
    chunks = [passage(n, text="x" * 2_500) for n in range(1, 41)]

    snap = answer_provenance.snapshot(chunks, [f"C{n}" for n in range(40, 0, -1)])

    assert [entry["label"] for entry in snap] == [f"C{n}" for n in range(1, 31)]
    assert {len(entry["text"]) for entry in snap} == {2_000}


def test_snapshot_of_an_answer_that_cites_nothing_is_empty():
    assert answer_provenance.snapshot([passage(1)], []) == []


async def test_save_answer_writes_the_cited_passages_in_the_same_row(session):
    paper = await make_paper(session, ["one", "two", "three"])
    prepared = await chat.prepare(session, paper.id, "why?")

    output_id = await chat.save_answer(session, paper.id, "why?", prepared, "Because [C3] and [C1].", "m", "Ollama")

    row = await session.get(LLMOutput, output_id)
    assert [entry["label"] for entry in row.source_snapshot] == ["C1", "C3"]
    assert row.source_snapshot[1] == {
        "label": "C3",
        "paper_id": str(paper.id),
        "page": 3,
        "section": None,
        "text": "three",
        "from_abstract": False,
    }


async def test_an_answer_that_cites_nothing_stores_an_empty_snapshot(session):
    paper = await make_paper(session, ["one", "two"])
    prepared = await chat.prepare(session, paper.id, "why?")

    output_id = await chat.save_answer(session, paper.id, "why?", prepared, "No source here.", "m", "Ollama")

    assert (await session.get(LLMOutput, output_id)).source_snapshot == []


async def test_save_brief_writes_the_cited_passages(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    prepared = await briefs.prepare_brief(session, paper.id, "key_ideas")

    output_id = await briefs.save_brief(
        session, paper.id, "key_ideas", prepared, "It claims X [C1] and Y [C3][C9].", "qwen3:8b", "Ollama"
    )

    row = await session.get(LLMOutput, output_id)
    assert [entry["label"] for entry in row.source_snapshot] == ["C1", "C3"]  # [C9] is no source


async def test_a_row_written_without_a_snapshot_keeps_it_null(session):
    paper = await make_paper(session, ["one"])
    row = LLMOutput(paper_id=paper.id, kind="chat", question="old", content="old [C1]", model="m", prompt_version=1)
    session.add(row)
    await session.commit()

    stored = await session.scalar(select(LLMOutput.source_snapshot).where(LLMOutput.id == row.id))
    assert stored is None


def drafts(texts: list[str]) -> list[ChunkDraft]:
    """What a re-ingest writes: every chunk new, on page n + 1, in reading order."""
    return [
        ChunkDraft(ordinal=i, page=i + 1, bbox=[[72, 100, 300, 120]], section_title=None, text=t)
        for i, t in enumerate(texts)
    ]


async def answer_citing(session, paper_id, content: str) -> uuid.UUID:
    prepared = await chat.prepare(session, paper_id, "why?")
    return await chat.save_answer(session, paper_id, "why?", prepared, content, "m", "Ollama")


async def test_a_reingest_keeps_each_citation_on_its_page_and_the_passage_still_in_the_paper(session):
    paper = await make_paper(session, ["one", "two", "three"])
    output_id = await answer_citing(session, paper.id, "Because [C3].")

    await papers.replace_chunks(session, paper.id, drafts(["one", "two", "three"]))  # same text, new chunk ids

    view = await answer_provenance.provenance(session, output_id)
    assert [(p.label, p.state, p.page, p.text) for p in view.passages] == [("C3", "current", 3, "three")]
    assert view.out_of_date is False
    [answer] = await chat.list_answers(session, paper.id)
    assert answer.sources == [None, None, None]  # the live chunks are gone...
    assert [(r.paper_id, r.page) for r in answer.replaced if r] == [(paper.id, 3)]  # ...and the snapshot keeps the page


async def test_a_cited_sentence_gone_from_the_paper_is_changed_and_makes_the_answer_out_of_date(session):
    paper = await make_paper(session, ["one", "two", "three"])
    output_id = await answer_citing(session, paper.id, "Because [C3].")

    await papers.replace_chunks(session, paper.id, drafts(["one", "two", "a new third part"]))

    view = await answer_provenance.provenance(session, output_id)
    assert [(p.label, p.state, p.text) for p in view.passages] == [("C3", "changed", "three")]
    assert view.out_of_date is True


async def test_a_title_edit_or_a_note_recolour_changes_nothing(session):
    paper = await make_paper(session, ["one", "two", "three"])
    output_id = await answer_citing(session, paper.id, "Because [C3].")
    session.add(Note(body="a note", provenance=Provenance.HUMAN, color="#ff0000"))
    await session.commit()

    await session.execute(update(Paper).where(Paper.id == paper.id).values(title="Another title"))
    await session.execute(update(Note).values(color="#00ff00"))
    await session.commit()

    view = await answer_provenance.provenance(session, output_id)
    assert [p.state for p in view.passages] == ["current"]
    assert view.out_of_date is False


async def test_an_answer_saved_before_m33_shows_live_passages_and_says_so_for_gone_ones(session):
    paper = await make_paper(session, ["one", "two", "three"])
    chunks = await chunks_of(session, paper.id)
    old = LLMOutput(
        paper_id=paper.id,
        kind="chat",
        question="old",
        content="[C1] and [C3]",
        model="m",
        prompt_version=1,
        source_chunks=[chunks[0].id, chunks[1].id, chunks[2].id],
        cited_chunks=[chunks[0].id, chunks[2].id],
    )
    session.add(old)
    await session.commit()

    await papers.replace_chunks(session, paper.id, drafts(["one", "two", "three"]))  # every chunk is replaced

    view = await answer_provenance.provenance(session, old.id)
    assert [(p.label, p.state, p.text, p.page) for p in view.passages] == [
        ("C1", "not_recorded", None, None),
        ("C3", "not_recorded", None, None),
    ]
    assert view.out_of_date is False


async def test_an_answer_saved_before_m33_with_its_chunks_still_there_shows_them_as_current(session):
    paper = await make_paper(session, ["one", "two"])
    chunks = await chunks_of(session, paper.id)
    old = LLMOutput(
        paper_id=paper.id,
        kind="chat",
        question="old",
        content="[C2]",
        model="m",
        prompt_version=1,
        source_chunks=[chunks[0].id, chunks[1].id],
        cited_chunks=[chunks[1].id],
    )
    session.add(old)
    await session.commit()

    view = await answer_provenance.provenance(session, old.id)
    assert [(p.label, p.state, p.text) for p in view.passages] == [("C2", "current", "two")]


async def test_a_workspace_answer_citing_40_passages_keeps_the_first_30_and_marks_the_rest_not_recorded(session):
    texts = [f"passage {n}" for n in range(1, 41)]
    paper = await make_paper(session, texts)
    output_id = await answer_citing(session, paper.id, " ".join(f"[C{n}]" for n in range(1, 41)))
    assert len((await session.get(LLMOutput, output_id)).source_snapshot) == 30

    view = await answer_provenance.provenance(session, output_id)

    assert len(view.passages) == 40
    assert [p.state for p in view.passages[:30]] == ["current"] * 30
    assert view.passages[29].text == "passage 30"
    assert [(p.label, p.state, p.page) for p in view.passages[30:32]] == [
        ("C31", "not_recorded", 31),
        ("C32", "not_recorded", 32),
    ]
    assert view.passages[31].text is None


async def test_a_citation_whose_chunk_was_deleted_still_points_at_its_page(session):
    paper = await make_paper(session, ["one", "two", "three"])
    await answer_citing(session, paper.id, "Because [C2].")

    await papers.replace_chunks(session, paper.id, drafts(["x", "y", "z"]))

    [answer] = await chat.list_answers(session, paper.id)
    assert answer.sources == [None, None, None]
    assert (answer.replaced[1].page, answer.replaced[1].paper_id, answer.replaced[1].from_abstract) == (
        2,
        paper.id,
        False,
    )


async def test_a_note_from_an_answer_gives_that_answers_provenance_and_an_mcp_note_says_so(session):
    paper = await make_paper(session, ["one", "two"])
    output_id = await answer_citing(session, paper.id, "Because [C1].")
    ai_note = Note(body="from the answer", provenance=Provenance.LLM, source_id=output_id)
    human = Note(body="mine", provenance=Provenance.HUMAN)
    mcp_output = LLMOutput(paper_id=paper.id, kind="mcp", content="added", model="mcp", prompt_version=0)
    session.add_all([ai_note, human, mcp_output])
    await session.flush()
    from_mcp = Note(body="from desktop", provenance=Provenance.LLM, source_id=mcp_output.id)
    session.add(from_mcp)
    await session.commit()

    assert (await answer_provenance.note_provenance(session, ai_note.id)).model == "m"
    assert isinstance(await answer_provenance.note_provenance(session, from_mcp.id), answer_provenance.McpNote)
    with pytest.raises(NotFound, match="not_ai"):
        await answer_provenance.note_provenance(session, human.id)
    with pytest.raises(NotFound, match="answer_not_found"):
        await answer_provenance.provenance(session, uuid.uuid4())


async def test_a_brief_citation_whose_chunk_was_replaced_keeps_its_page(session):
    paper, _ = await paper_with_headings(session, HEADINGS)
    prepared = await briefs.prepare_brief(session, paper.id, "key_ideas")
    await briefs.save_brief(session, paper.id, "key_ideas", prepared, "It claims X [C1].", "m", "Ollama")
    await papers.replace_chunks(session, paper.id, drafts(["a", "b", "c", "d", "e", "f"]))

    [brief] = await briefs.list_briefs(session, paper.id)

    assert brief.sources[0] is None
    assert (brief.replaced[0].page, brief.replaced[0].paper_id) == (1, paper.id)
