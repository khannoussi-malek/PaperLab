import uuid

import pytest
from sqlalchemy import delete, select
from test_chat import chunks_of, make_paper

from app.core import chat
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
    assert thread.source_ids == [three, one, two, one]  # repeats are fine: follow_up_sources keeps each once


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
