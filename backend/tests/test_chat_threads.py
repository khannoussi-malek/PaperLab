import uuid

import numpy as np
import pytest
from conftest import unit_vector
from sqlalchemy import delete, select
from test_chat import chunks_of, make_paper

from app.core import chat, papers
from app.core.errors import Conflict, NotFound
from app.models import LLMOutput, Workspace

pytestmark = pytest.mark.anyio


async def answer(
    session, paper_id, question: str | None, sources=(), parent: LLMOutput | None = None, kind="chat", **fields
) -> LLMOutput:
    output = LLMOutput(
        paper_id=paper_id, kind=kind, question=question, content="An answer.", model="m", prompt_version=2,
        source_chunks=list(sources), parent_id=parent.id if parent else None, **fields,
    )
    session.add(output)
    await session.flush()
    return output


async def test_a_thread_carries_its_questions_oldest_first_and_passages_newest_answer_first(session):
    paper = await make_paper(session, ["one", "two", "three"])
    one, two, three = [chunk.id for chunk in await chunks_of(session, paper.id)]
    first = await answer(session, paper.id, "What is it?", [one])
    second = await answer(session, paper.id, "How big is it?", [two], parent=first)
    third = await answer(session, paper.id, "And later?", [three, one], parent=second)

    thread = await chat.load_thread(session, paper.id, third.id)

    assert thread.questions == ["What is it?", "How big is it?", "And later?"]
    # Newest answer first, each passage once, and each answer's passages its parent didn't have ahead of the rest.
    assert thread.source_ids == [three, one, two]


async def test_a_thread_keeps_only_the_five_nearest_answers(session):
    paper = await make_paper(session, ["one"])
    parent = None
    for i in range(7):
        parent = await answer(session, paper.id, f"Question {i}?", parent=parent)

    thread = await chat.load_thread(session, paper.id, parent.id)

    assert thread.questions == [f"Question {i}?" for i in range(2, 7)]


async def test_a_thread_follows_a_chat_answer_on_the_same_paper(session):
    paper, other = await make_paper(session, ["one"]), await make_paper(session, ["two"])
    elsewhere = await answer(session, other.id, "Elsewhere?")
    brief = await answer(session, paper.id, None, kind="brief")
    workspace = Workspace(name=f"Threads {uuid.uuid4().hex[:6]}")
    session.add(workspace)
    await session.flush()
    in_workspace = await answer(session, None, "Across papers?", workspace_id=workspace.id)

    for missing in (uuid.uuid4(), brief.id):
        with pytest.raises(NotFound, match="parent_not_found"):
            await chat.load_thread(session, paper.id, missing)
    for foreign in (elsewhere.id, in_workspace.id):
        with pytest.raises(Conflict, match="parent_scope"):
            await chat.load_thread(session, paper.id, foreign)
    with pytest.raises(NotFound, match=r"^paper .* not found$"):  # an unknown paper is a 404 before its parent is read
        await chat.load_thread(session, uuid.uuid4(), elsewhere.id)


async def test_deleting_an_answer_makes_its_follow_up_the_start_of_a_thread(session):
    paper = await make_paper(session, ["one"])
    first = await answer(session, paper.id, "First?")
    second = await answer(session, paper.id, "Second?", parent=first)

    await session.execute(delete(LLMOutput).where(LLMOutput.id == first.id))

    assert await session.scalar(select(LLMOutput.parent_id).where(LLMOutput.id == second.id)) is None


async def test_save_answer_records_the_answer_it_follows(session):
    paper = await make_paper(session, ["one"])
    first = await answer(session, paper.id, "First?")
    prepared = await chat.prepare(session, paper.id, "Then?")

    output_id = await chat.save_answer(
        session, paper.id, "Then?", prepared, "Yes [C1].", "m", "Ollama", parent_id=first.id
    )

    assert (await session.get(LLMOutput, output_id)).parent_id == first.id


async def test_a_second_follow_up_carries_the_passages_the_first_follow_up_found(session, embedder):
    # Three groups of 8 passages; each question's query vector sits between one group's vectors, so it retrieves
    # exactly that group. The paper is over SMALL_PAPER_CHARS, so follow-ups mix earlier and fresh passages.
    run = uuid.uuid4().hex  # unique vectors: dead HNSW entries from earlier runs never crowd these queries
    texts = [f"{run} group {g} part {i} " + "x" * 1_200 for g in range(3) for i in range(8)]
    paper = await make_paper(session, texts)
    chunks = await chunks_of(session, paper.id)
    groups = [{chunk.id for chunk in chunks[8 * g : 8 * g + 8]} for g in range(3)]
    questions = ["What is S1?", "And S2?", "Why does that happen?"]
    for g, question in enumerate(questions):
        centre = np.sum([unit_vector(text) for text in texts[8 * g : 8 * g + 8]], axis=0)
        embedder.vectors[f"search_query: {question}"] = list(centre / np.linalg.norm(centre))

    parent_id, prepared = None, None
    for question in questions:
        thread = None if parent_id is None else await chat.load_thread(session, paper.id, parent_id)
        prepared = await chat.prepare(session, paper.id, question, embedder, thread=thread)
        parent_id = await chat.save_answer(session, paper.id, question, prepared, "An answer.", "m", "c", parent_id)

    ids = {source.id for source in prepared.sources}
    assert groups[2] <= ids  # every fresh passage
    assert ids - groups[2] <= groups[1] and len(ids - groups[2]) == chat.FOLLOW_UP_SOURCES - 8  # carried: the last hop


async def test_deleting_a_paper_deletes_its_threads(session):
    paper = await make_paper(session, ["one"])
    first = await answer(session, paper.id, "First?")
    second = await answer(session, paper.id, "Second?", parent=first)
    await answer(session, paper.id, "Third?", parent=second)

    await papers.delete_paper(session, paper.id)

    assert (await session.scalars(select(LLMOutput.id).where(LLMOutput.paper_id == paper.id))).all() == []
