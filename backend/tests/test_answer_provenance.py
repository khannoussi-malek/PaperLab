"""M33: an answer keeps a copy of the passages it cited (llm_outputs.source_snapshot), written with the answer."""

import uuid

import pytest
from sqlalchemy import select
from test_chat import make_paper
from test_sections import paper_with_headings

from app.core import answer_provenance, briefs, chat
from app.core.retrieval import RetrievedChunk
from app.models import LLMOutput

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
