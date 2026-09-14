import uuid

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from app.core import papers
from app.models import LLMOutput, Note, Paper, Provenance, Workspace

pytestmark = pytest.mark.anyio


async def make_output(session, **fields) -> LLMOutput:
    paper = Paper(title="answered paper", file_path="/nonexistent.pdf", page_count=1)
    session.add(paper)
    await session.flush()
    output = LLMOutput(paper_id=paper.id, kind="chat", content="an answer", model="fake", prompt_version=1, **fields)
    session.add(output)
    await session.commit()
    return output


async def test_chat_columns_round_trip_in_order(session):
    sources = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    output = await make_output(session, question="why?", source_chunks=sources, cited_chunks=[sources[2]])

    await session.refresh(output)

    assert (output.question, output.source_chunks, output.cited_chunks) == ("why?", sources, [sources[2]])
    assert output.whole_paper is False


async def test_deleting_a_paper_keeps_notes_promoted_from_its_answers(session):
    output = await make_output(session)
    note = Note(body="an answer", provenance=Provenance.LLM, source_id=output.id)
    session.add(note)
    await session.commit()

    await papers.delete_paper(session, output.paper_id)
    await session.refresh(note)

    assert (note.provenance, note.source_id) == (Provenance.LLM, None)


async def test_a_workspace_answer_stores_its_notes_and_arrays_default_to_empty(session):
    workspace = Workspace(name=f"Answers {uuid.uuid4()}")
    session.add(workspace)
    await session.flush()
    note_ids = [uuid.uuid4(), uuid.uuid4()]
    output = LLMOutput(
        workspace_id=workspace.id, kind="chat", content="a", model="fake", prompt_version=1,
        source_notes=note_ids, notes_used=2, notes_total=5,
    )
    session.add(output)
    await session.commit()

    await session.refresh(output)

    assert (output.paper_id, output.source_notes, output.notes_used, output.notes_total) == (None, note_ids, 2, 5)
    assert (output.source_chunks, output.cited_chunks) == ([], [])


@pytest.mark.parametrize(
    ("scope", "violation"),
    [("neither", "llm_outputs_chat_scope"), ("both", "llm_outputs_chat_scope"), ("null_cited", "cited_chunks")],
)
async def test_a_chat_answer_needs_exactly_one_scope_and_non_null_citations(session, scope, violation):
    paper = Paper(title="answered paper", file_path="/nonexistent.pdf")
    workspace = Workspace(name=f"Answers {uuid.uuid4()}")
    session.add_all([paper, workspace])
    await session.flush()
    fields = {
        "neither": {},
        "both": {"paper_id": paper.id, "workspace_id": workspace.id},
        "null_cited": {"paper_id": paper.id, "cited_chunks": None},
    }[scope]

    # A Core insert: the ORM leaves out a None for a column with a server default.
    row = {"kind": "chat", "content": "a", "model": "fake", "prompt_version": 1, **fields}
    with pytest.raises(IntegrityError, match=violation):
        await session.execute(insert(LLMOutput).values(**row))
