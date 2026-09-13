import uuid

import pytest

from app.core import papers
from app.models import LLMOutput, Note, Paper, Provenance

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
