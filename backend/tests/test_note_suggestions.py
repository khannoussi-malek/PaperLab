import uuid

import pytest
from test_chat import make_paper

from app.core.errors import Conflict
from app.core.note_suggestions import NOTE_SUGGESTIONS_PROMPT_VERSION, _sample_evenly, save_suggestions, suggest
from app.core.retrieval import RetrievedChunk
from app.models import LLMOutput
from app.providers.llm import FAKE_NOTE_SUGGESTIONS, FakeLLM

pytestmark = pytest.mark.anyio


def chunk(i: int) -> RetrievedChunk:
    return RetrievedChunk(id=uuid.uuid4(), paper_id=uuid.uuid4(), page=i + 1, section=None, bbox=[], text=f"passage {i}")


def test_sample_evenly_returns_everything_when_there_are_fewer_chunks_than_k():
    chunks = [chunk(i) for i in range(3)]

    assert _sample_evenly(chunks, 6) == chunks


def test_sample_evenly_spreads_across_the_whole_paper_first_to_last():
    chunks = [chunk(i) for i in range(30)]

    sample = _sample_evenly(chunks, 6)

    assert [chunks.index(c) for c in sample] == [0, 5, 10, 15, 20, 25]  # step = 30/6 = 5, evenly spread
    assert sample[0] is chunks[0] and sample[-1] is not chunks[-1]  # covers the start; doesn't reach past ~step*(k-1)


def test_sample_evenly_never_returns_duplicates_when_the_step_rounds_down_to_repeat_an_index():
    chunks = [chunk(i) for i in range(4)]  # step = 4/3 ≈ 1.33 -> int(0), int(1.33)=1, int(2.66)=2 for k=3

    sample = _sample_evenly(chunks, 3)

    assert len(sample) == len({c.id for c in sample})


async def test_suggest_parses_one_note_per_labeled_line(session):
    paper = await make_paper(session, ["one", "two", "three"])
    llm = FakeLLM()

    result = await suggest(session, paper.id, llm)

    # FAKE_NOTE_SUGGESTIONS deliberately covers C1 and C3, skipping C2 -- the model choosing not to cover every
    # passage is a real, expected outcome, not a bug.
    assert [(s.body, s.source.text) for s in result.suggestions] == [
        ("Fake first passage note.", "one"),
        ("Fake third passage note.", "three"),
    ]
    assert result.content == FAKE_NOTE_SUGGESTIONS
    assert len(result.sources) == 3  # every chunk sent, not just the ones the model covered


async def test_suggest_drops_a_line_whose_label_is_out_of_range(session):
    paper = await make_paper(session, ["one"])

    class OverclaimingLLM(FakeLLM):
        async def stream(self, system, prompt):
            self.calls.append((system, prompt))
            yield "[C1]: Real.\n[C9]: Out of range, dropped.\n[C0]: Also out of range, dropped."

    result = await suggest(session, paper.id, OverclaimingLLM())

    assert [s.body for s in result.suggestions] == ["Real."]


async def test_suggest_raises_conflict_for_a_paper_not_ready(session):
    paper = await make_paper(session, ["one"], status="chunking")

    with pytest.raises(Conflict, match="paper_not_ready"):
        await suggest(session, paper.id, FakeLLM())


async def test_suggest_raises_conflict_for_an_unindexed_paper(session):
    paper = await make_paper(session, [])  # ready, but no chunks at all

    with pytest.raises(Conflict, match="paper_not_indexed"):
        await suggest(session, paper.id, FakeLLM())


async def test_save_suggestions_stores_kind_note_suggestions_not_chat(session):
    """So a suggestion generation never shows up in the paper's chat history (chat.list_answers filters on
    kind == "chat"), and so an accepted suggestion can still be promoted through the exact same
    notes.promote_llm_fragment a chat answer's own selection uses -- it only cares about content/source_chunks,
    never kind."""
    paper = await make_paper(session, ["one", "two"])
    result = await suggest(session, paper.id, FakeLLM())

    output_id = await save_suggestions(session, paper.id, result, "fake", "Fake")

    output = await session.get(LLMOutput, output_id)
    assert output.kind == "note_suggestions"
    assert output.content == result.content
    assert set(output.source_chunks) == {c.id for c in result.sources}
    assert set(output.cited_chunks) == {s.source.id for s in result.suggestions}
    assert (output.model, output.connection_name, output.prompt_version) == (
        "fake", "Fake", NOTE_SUGGESTIONS_PROMPT_VERSION,
    )
