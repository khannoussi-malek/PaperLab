import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select
from test_chat import make_paper

from app.core import chat, voice_turn
from app.core.voice_turn import TurnResult, finish_whole, run_turn, save_heard
from app.models import LLMOutput, Paper
from app.models.voice_turn import VoiceTurn
from app.providers import embedding
from app.providers.base import SpeechUnavailable
from app.providers.llm import FakeLLM
from app.providers.speech import FakeSpeech

pytestmark = pytest.mark.anyio

SENTENCES = ["First sentence is here.", " Second sentence is here.", " Third sentence is here."]


class ScriptedLLM:
    """Streams exactly these tokens."""

    model, connection_name, host = "scripted", "Scripted", "test"

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.calls: list[tuple[str, str]] = []

    async def stream(self, system: str, prompt: str):
        self.calls.append((system, prompt))
        for token in self.tokens:
            yield token


class GatedSpeech(FakeSpeech):
    """The second speak call waits until the test lets it go."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gate = asyncio.Event()

    async def speak(self, text: str):
        if self.spoken:
            await self.gate.wait()
        return await super().speak(text)


class FailingSpeech(FakeSpeech):
    """Speaks the first sentence, then the voice program goes away."""

    async def speak(self, text: str):
        if self.spoken:
            raise SpeechUnavailable("The voice program isn't running. Start it with scripts/voice.sh.")
        return await super().speak(text)


class StallingLLM(ScriptedLLM):
    """One token, then it waits for ever."""

    async def stream(self, system: str, prompt: str):
        yield self.tokens[0]
        await asyncio.Event().wait()


class DownSpeech(FakeSpeech):
    async def transcribe(self, samples: bytes) -> str:
        raise SpeechUnavailable("The voice program isn't running. Start it with scripts/voice.sh.")


@pytest.fixture
def sent():
    return []


@pytest.fixture
def send(sent):
    async def _send(message):
        sent.append(message)

    return _send


@pytest.fixture
def make_turn(session, answers_in_test_transaction):
    async def _make(texts=("Intro text.", "Method text."), **fields):
        paper = await make_paper(session, list(texts))
        return paper, TurnResult(scope=chat.Scope(paper_id=paper.id), cold=fields.pop("cold", False), **fields)

    return _make


def types(sent) -> list[str]:
    return ["audio" if isinstance(m, bytes) else m["type"] for m in sent]


async def rows(session, model):
    return list(await session.scalars(select(model)))


async def test_a_turn_sends_transcript_sources_tokens_then_audio_then_done_and_saves_nothing_yet(
    make_turn, session, send, sent
):
    paper, result = await make_turn()
    llm = FakeLLM()

    await run_turn(result, b"\0" * 64, llm, FakeSpeech(), send)

    order = types(sent)
    assert order[:3] == ["turn", "transcript", "sources"]
    assert order[-1] == "done"
    middle = order[3:-1]
    assert set(middle) == {"token", "sentence", "audio"}
    assert all(order[i + 1] == "audio" for i, kind in enumerate(order) if kind == "sentence")
    assert sent[0] == {"type": "turn", "id": str(result.turn_id)}
    assert sent[1] == {"type": "transcript", "text": "What does this paper say?"}
    assert sent[2]["whole_paper"] is True and sent[2]["sources"][0]["label"] == "C1"
    sentence = next(m for m in sent if isinstance(m, dict) and m["type"] == "sentence")
    assert sentence["seq"] == 0 and sentence["rate"] == 24000
    assert await rows(session, LLMOutput) == [] and await rows(session, VoiceTurn) == []


async def test_finish_whole_saves_the_whole_answer_with_its_whitespace_and_one_timing_row(make_turn, session, send):
    paper, result = await make_turn(cold=True)
    tokens = ["First sentence is here.\n\n", "Second  sentence [C1] is here.\n"]

    await run_turn(result, b"", ScriptedLLM(tokens), FakeSpeech(), send)
    output_id = await finish_whole(result, ScriptedLLM(tokens))

    output = await session.get(LLMOutput, output_id)
    assert output.content == "".join(tokens) == result.answer
    assert (output.paper_id, output.kind, output.question) == (paper.id, "chat", "What does this paper say?")
    assert (output.model, output.connection_name) == ("scripted", "Scripted")
    [row] = await rows(session, VoiceTurn)
    assert row.id == result.row_id
    assert (row.paper_id, row.workspace_id, row.cold, row.whole_paper, row.interrupted) == (
        paper.id,
        None,
        True,
        True,
        False,
    )
    assert (row.model, row.connection_name) == ("scripted", "Scripted")
    assert await session.scalar(select(func.count()).select_from(LLMOutput)) == 1


async def test_markers_reach_the_screen_but_never_the_speech(make_turn, send, sent):
    _, result = await make_turn()
    speech = FakeSpeech()

    await run_turn(result, b"", FakeLLM(), speech, send)

    assert speech.spoken and not any("[C" in text for text in speech.spoken)
    shown = "".join(m["text"] for m in sent if isinstance(m, dict) and m["type"] == "token")
    assert "[C1]" in shown


async def test_a_chunk_of_only_markers_is_not_spoken(make_turn, send, sent):
    _, result = await make_turn()
    speech = FakeSpeech()
    tokens = ["[C1]\n", "Next sentence is spoken."]

    await run_turn(result, b"", ScriptedLLM(tokens), speech, send)

    assert speech.spoken == ["Next sentence is spoken."]
    assert [text for text, _ in result.chunks] == ["[C1] Next sentence is spoken."]
    assert result.answer == "[C1]\nNext sentence is spoken."
    assert "[C1]\n" in [m["text"] for m in sent if isinstance(m, dict) and m["type"] == "token"]
    assert types(sent).count("audio") == 1
    sentence = next(m for m in sent if isinstance(m, dict) and m["type"] == "sentence")
    assert sentence["text"] == result.chunks[0][0] == "[C1] Next sentence is spoken."


async def test_empty_transcript_sends_done_without_calling_the_model_or_saving(make_turn, session, send, sent):
    _, result = await make_turn()
    llm = FakeLLM()

    await run_turn(result, b"", llm, FakeSpeech(transcript="   "), send)

    assert types(sent) == ["turn", "done"]
    assert llm.calls == []
    assert result.row_id is None
    assert await rows(session, LLMOutput) == [] and await rows(session, VoiceTurn) == []


async def test_speech_unavailable_at_transcribe_sends_error_and_saves_nothing(make_turn, session, send, sent):
    _, result = await make_turn()
    llm = FakeLLM()

    await run_turn(result, b"", llm, DownSpeech(), send)

    assert sent[-1] == {
        "type": "error",
        "message": "The voice program isn't running. Start it with scripts/voice.sh.",
        "retryable": True,
    }
    assert "done" not in types(sent) and llm.calls == []
    assert await rows(session, LLMOutput) == [] and await rows(session, VoiceTurn) == []


async def test_model_failure_mid_answer_sends_error_and_saves_nothing(make_turn, session, send, sent):
    _, result = await make_turn()

    await run_turn(result, b"", FakeLLM(fail_after=2), FakeSpeech(), send)

    assert sent[-1] == {"type": "error", "message": "fake model failed mid-answer", "retryable": True}
    assert "done" not in types(sent)
    assert await rows(session, LLMOutput) == []


async def test_a_refused_question_is_told_in_the_typed_chats_words(session, answers_in_test_transaction, send, sent):
    paper = await make_paper(session, ["Intro text."], status="extracting")
    result = TurnResult(scope=chat.Scope(paper_id=paper.id), cold=False)
    llm = FakeLLM()

    await run_turn(result, b"", llm, FakeSpeech(), send)

    assert sent[-1] == {
        "type": "error",
        "message": "This paper is still being processed. Ask again once it is ready.",
        "retryable": True,
    }
    assert llm.calls == []


async def test_timing_row_records_each_stage_and_cold(make_turn, session, send):
    _, result = await make_turn(cold=True)

    await run_turn(result, b"", FakeLLM(), FakeSpeech(delay=0.02), send)
    await finish_whole(result, FakeLLM())

    [row] = await rows(session, VoiceTurn)
    assert row.cold is True
    for name in ("stt_ms", "retrieval_ms", "ttft_ms", "first_chunk_ms", "tts_first_ms", "first_audio_sent_ms"):
        assert getattr(row, name) is not None, name
    assert row.tts_first_ms >= 20
    assert row.first_audio_sent_ms >= row.tts_first_ms
    assert (row.embed_ms, row.wait_ms, row.output_ms, row.total_ms, row.interrupt_stop_ms) == (None,) * 5
    assert row.prompt_chars == len(result.prepared.system) + len(result.prepared.prompt)


async def test_a_failed_turn_writes_its_timing_row_and_no_answer(make_turn, session, send):
    paper, result = await make_turn()

    await run_turn(result, b"", FakeLLM(fail_after=2), FakeSpeech(), send)

    [row] = await rows(session, VoiceTurn)
    assert row.id == result.row_id and row.paper_id == paper.id
    assert row.stt_ms is not None and row.ttft_ms is not None
    assert await rows(session, LLMOutput) == []


async def test_a_parent_id_makes_the_turn_a_follow_up_and_saves_it_under_that_answer(make_turn, session, send):
    paper, first = await make_turn()
    llm = FakeLLM()
    await run_turn(first, b"", llm, FakeSpeech(transcript="What was the method?"), send)
    parent_id = await finish_whole(first, llm)

    second = TurnResult(scope=chat.Scope(paper_id=paper.id), cold=False, parent_id=parent_id)
    await run_turn(second, b"", llm, FakeSpeech(transcript="And its limits?"), send)
    follow_up_id = await finish_whole(second, llm)

    assert (await session.get(LLMOutput, follow_up_id)).parent_id == parent_id
    assert "What was the method?" in llm.calls[1][1]


async def test_embed_time_is_set_for_a_searched_paper_and_empty_for_a_whole_one(
    make_turn, session, send, embedder, monkeypatch
):
    monkeypatch.setattr(embedding, "get_model", lambda: embedder)
    _, small = await make_turn()
    _, large = await make_turn(texts=[f"chunk {i} " + "x" * 2_100 for i in range(12)])
    llm = FakeLLM()

    await run_turn(small, b"", llm, FakeSpeech(), send)
    await run_turn(large, b"", llm, FakeSpeech(), send)
    await finish_whole(small, llm)
    await finish_whole(large, llm)

    by_id = {row.id: row for row in await rows(session, VoiceTurn)}
    assert (small.prepared.whole_paper, large.prepared.whole_paper) == (True, False)
    assert by_id[small.row_id].whole_paper is True and by_id[small.row_id].embed_ms is None
    assert by_id[large.row_id].whole_paper is False and by_id[large.row_id].embed_ms is not None


async def start_cancelled_after_first_chunk(result, llm, speech, send):
    task = asyncio.create_task(run_turn(result, b"", llm, speech, send))
    while not result.chunks:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelling_stops_further_audio_and_save_heard_keeps_only_what_was_heard(make_turn, session, send, sent):
    _, result = await make_turn()
    llm, speech = ScriptedLLM(SENTENCES), GatedSpeech()

    await start_cancelled_after_first_chunk(result, llm, speech, send)
    audio_at_cancel = types(sent).count("audio")
    speech.gate.set()
    await asyncio.sleep(0.01)
    output_id = await save_heard(result, result.chunks[0][1], llm, stop_ms=120)

    assert audio_at_cancel == 1 and types(sent).count("audio") == 1
    assert "done" not in types(sent)
    assert (await session.get(LLMOutput, output_id)).content == "First sentence is here.…"
    [row] = await rows(session, VoiceTurn)
    assert (row.interrupted, row.interrupt_stop_ms, row.id) == (True, 120, result.row_id)


async def test_an_interruption_after_all_audio_was_sent_still_saves_only_what_was_heard(make_turn, session, send, sent):
    _, result = await make_turn()
    llm = ScriptedLLM(SENTENCES)

    await run_turn(result, b"", llm, FakeSpeech(), send)
    assert sent[-1] == {"type": "done"}
    output_id = await save_heard(result, result.chunks[0][1], llm, stop_ms=None)

    content = (await session.get(LLMOutput, output_id)).content
    assert content == "First sentence is here.…"
    assert "Third" not in content


async def test_save_heard_with_nothing_heard_saves_nothing_and_returns_none(make_turn, session, send):
    _, result = await make_turn()
    llm = ScriptedLLM(SENTENCES)

    await run_turn(result, b"", llm, FakeSpeech(), send)

    assert await save_heard(result, 0.0, llm, stop_ms=None) is None
    assert await rows(session, LLMOutput) == []
    [row] = await rows(session, VoiceTurn)
    assert row.interrupted is True


async def test_a_deleted_paper_keeps_its_timing_rows(make_turn, session, send):
    paper, result = await make_turn()
    llm = FakeLLM()
    await run_turn(result, b"", llm, FakeSpeech(), send)
    await finish_whole(result, llm)

    await session.execute(delete(Paper).where(Paper.id == paper.id))
    session.expire_all()

    [row] = await rows(session, VoiceTurn)
    assert row.paper_id is None and uuid.UUID(str(row.id)) == result.row_id


async def test_a_trailing_marker_only_chunk_stays_with_the_last_spoken_chunk(make_turn, send):
    _, result = await make_turn()
    speech = FakeSpeech()

    await run_turn(result, b"", ScriptedLLM(["First sentence is here.\n", "[C2]"]), speech, send)

    assert speech.spoken == ["First sentence is here."]
    assert [text for text, _ in result.chunks] == ["First sentence is here. [C2]"]
    assert result.answer == "First sentence is here.\n[C2]"


async def test_finish_whole_after_an_empty_transcript_returns_none(make_turn, session, send):
    _, result = await make_turn()
    llm = FakeLLM()

    await run_turn(result, b"", llm, FakeSpeech(transcript=" "), send)

    assert await finish_whole(result, llm) is None
    assert await save_heard(result, 1.0, llm, stop_ms=None) is None
    assert await rows(session, LLMOutput) == [] and await rows(session, VoiceTurn) == []


async def test_a_second_save_returns_the_first_id_and_writes_nothing(make_turn, session, send):
    llm = FakeLLM()
    _, whole = await make_turn()
    _, cut = await make_turn()
    await run_turn(whole, b"", llm, FakeSpeech(), send)
    await run_turn(cut, b"", llm, FakeSpeech(), send)

    first = await finish_whole(whole, llm)
    assert await finish_whole(whole, llm) == first
    assert await save_heard(whole, 0.005, llm, stop_ms=None) == first
    heard = await save_heard(cut, cut.chunks[0][1], llm, stop_ms=80)
    assert await save_heard(cut, cut.chunks[0][1], llm, stop_ms=80) == heard
    assert await finish_whole(cut, llm) == heard

    assert heard is not None and heard != first
    assert await session.scalar(select(func.count()).select_from(LLMOutput)) == 2
    assert await session.scalar(select(func.count()).select_from(VoiceTurn)) == 2


async def test_save_heard_after_a_failed_turn_writes_nothing_more(make_turn, session, send):
    _, result = await make_turn()
    llm = FakeLLM(fail_after=2)

    await run_turn(result, b"", llm, FakeSpeech(), send)

    assert await save_heard(result, 1.0, llm, stop_ms=50) is None
    assert await finish_whole(result, llm) is None
    assert await rows(session, LLMOutput) == []
    [row] = await rows(session, VoiceTurn)
    assert row.interrupted is False and row.id == result.row_id


async def test_a_timing_row_failure_still_returns_the_saved_answer(make_turn, session, send, monkeypatch):
    llm = FakeLLM()
    _, whole = await make_turn()
    _, cut = await make_turn()
    await run_turn(whole, b"", llm, FakeSpeech(), send)
    await run_turn(cut, b"", llm, FakeSpeech(), send)

    async def broken(*args, **kwargs):
        raise RuntimeError("the timing row could not be written")

    monkeypatch.setattr(voice_turn, "_record", broken)

    whole_id = await finish_whole(whole, llm)
    cut_id = await save_heard(cut, cut.chunks[0][1], llm, stop_ms=None)

    assert (await session.get(LLMOutput, whole_id)).content == whole.answer
    assert (await session.get(LLMOutput, cut_id)).content.endswith("…")


async def test_speech_failing_mid_answer_sends_error_and_saves_nothing_yet(make_turn, session, send, sent):
    _, result = await make_turn()

    await run_turn(result, b"", ScriptedLLM(SENTENCES), FailingSpeech(), send)

    assert sent[-1] == {
        "type": "error",
        "message": "The voice program isn't running. Start it with scripts/voice.sh.",
        "retryable": True,
    }
    assert "done" not in types(sent) and types(sent).count("audio") == 1
    assert await rows(session, LLMOutput) == []


async def test_cancelling_during_the_token_stream_stops_cleanly(make_turn, session, send, sent):
    _, result = await make_turn()
    llm = StallingLLM(["First "])
    before = asyncio.all_tasks()

    task = asyncio.create_task(run_turn(result, b"", llm, FakeSpeech(), send))
    while not result.answer:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert asyncio.all_tasks() == before  # neither the model task nor the speaking task is left running
    assert "done" not in types(sent) and "error" not in types(sent)
    assert result.answer == "First "
    assert await save_heard(result, 1.0, llm, stop_ms=None) is None
    assert await rows(session, LLMOutput) == []


async def test_mark_false_interrupt_flags_only_that_row(make_turn, session, send):
    _, first = await make_turn()
    await run_turn(first, b"", ScriptedLLM(SENTENCES), FakeSpeech(), send)
    await save_heard(first, 0.1, ScriptedLLM(SENTENCES), stop_ms=50)
    _, other = await make_turn()
    await run_turn(other, b"", ScriptedLLM(SENTENCES), FakeSpeech(), send)
    await finish_whole(other, ScriptedLLM(SENTENCES))

    await voice_turn.mark_false_interrupt(first.row_id)

    flags = {row.id: row.false_interrupt for row in await rows(session, VoiceTurn)}
    assert flags == {first.row_id: True, other.row_id: False}
