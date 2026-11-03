"""WS /api/voice/ws, with run_turn, the saves and the database lookups replaced: Starlette's TestClient runs its own
event loop, so the turn's database work is covered in test_voice_turn.py. The replacement run_turn follows the real
one: it sends `turn`, fills the TurnResult and honours cancellation."""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import voice
from app.api.deps import resolve_speech
from app.core.errors import NotFound
from app.main import create_app
from app.providers.llm import FakeLLM
from app.providers.speech import FakeSpeech

TALK, SLOW, MUTE = b"talk", b"slow", b"mute"  # 4 bytes each: one float32 sample
START = {"type": "start", "scope": "paper", "id": str(uuid.uuid4()), "model_id": None}
LOCAL = {"origin": "http://localhost:5173"}


@pytest.fixture
def rig(monkeypatch):
    seen, saved, cancelled, false_marks = [], [], [], []
    speech = FakeSpeech()

    async def run_turn(result, samples, llm, speech, send):
        seen.append(SimpleNamespace(result=result, llm=llm, speech=speech, parent=result.parent_id, cold=result.cold))
        await send({"type": "turn", "id": str(result.turn_id)})
        if samples == MUTE:  # noise: no transcript, no row
            await send({"type": "done"})
            return
        result.question = "What?"
        result.answer = "Whole answer."
        await send({"type": "transcript", "text": result.question})
        if samples == SLOW:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(result.turn_id)
                raise
        await send({"type": "done"})

    async def finish_whole(result, llm):
        result.row_id = uuid.uuid4()
        result.output_id = uuid.uuid4()
        saved.append(SimpleNamespace(kind="whole", result=result, llm=llm))
        return result.output_id

    async def save_heard(result, played_seconds, llm, stop_ms):
        assert result.turn_id in cancelled or result.answer  # a running turn is stopped first
        result.row_id = uuid.uuid4()
        result.output_id = uuid.uuid4() if played_seconds > 0 else None  # nothing heard: no answer
        saved.append(SimpleNamespace(kind="heard", result=result, llm=llm, played=played_seconds, stop_ms=stop_ms))
        return result.output_id

    async def load_llm(model_id, transport):
        return FakeLLM()

    async def mark_false_interrupt(row_id):
        false_marks.append(row_id)

    monkeypatch.setattr(voice, "run_turn", run_turn)
    monkeypatch.setattr(voice, "finish_whole", finish_whole)
    monkeypatch.setattr(voice, "save_heard", save_heard)
    monkeypatch.setattr(voice, "load_llm", load_llm)
    monkeypatch.setattr(voice, "mark_false_interrupt", mark_false_interrupt)
    app = create_app()
    app.dependency_overrides[resolve_speech] = lambda: speech
    return SimpleNamespace(
        client=TestClient(app), seen=seen, saved=saved, cancelled=cancelled, false_marks=false_marks, speech=speech
    )


def connect(rig, **headers):
    return rig.client.websocket_connect("/api/voice/ws", headers=headers or LOCAL)


def started(ws, **start):
    ws.send_json({**START, **start})


def until(ws, kind):
    """Messages up to and including the first of this type."""
    messages = []
    while True:
        messages.append(ws.receive_json())
        if messages[-1]["type"] == kind:
            return messages


def ask(ws, samples=TALK):
    ws.send_bytes(samples)
    return until(ws, "done")


def closed_with(ws) -> int:
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    return closed.value.code


def test_a_foreign_origin_is_refused_with_4403(rig):
    with pytest.raises(WebSocketDisconnect) as closed:
        with connect(rig, origin="http://evil.example"):
            pass
    assert closed.value.code == 4403


def test_a_local_origin_and_no_origin_are_accepted(rig):
    for headers in ({"origin": "http://127.0.0.1:5173"}, {"origin": "http://localhost:8000"}, {"x-none": "1"}):
        with rig.client.websocket_connect("/api/voice/ws", headers=headers) as ws:
            started(ws)
            assert ask(ws)[0]["type"] == "turn"


def test_utterance_before_start_is_refused_with_4400(rig):
    with connect(rig) as ws:
        ws.send_bytes(TALK)
        assert closed_with(ws) == 4400
    assert rig.seen == []


def test_bad_start_message_is_refused_with_4400(rig):
    for bad in ("not json", '{"type":"start","scope":"galaxy","id":"x"}', '{"type":"interrupt","played_seconds":1}'):
        with connect(rig) as ws:
            ws.send_text(bad)
            assert closed_with(ws) == 4400


def test_finished_saves_the_whole_answer_and_sends_saved(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "finished"})
        message = ws.receive_json()
        ws.send_json({"type": "finished"})  # a second one finds nothing to save
        assert ask(ws)[0]["type"] == "turn"
    [only] = rig.saved
    assert only.kind == "whole" and message == {"type": "saved", "output_id": str(only.result.output_id)}
    assert isinstance(only.llm, FakeLLM)


def test_interrupt_after_done_saves_only_what_was_heard_and_sends_saved(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "interrupt", "played_seconds": 1.5, "stop_ms": 120})
        message = ws.receive_json()
    [only] = rig.saved
    assert (only.kind, only.played, only.stop_ms) == ("heard", 1.5, 120)
    assert message == {"type": "saved", "output_id": str(only.result.output_id)}


def test_finished_with_no_answer_is_ignored(rig):
    with connect(rig) as ws:
        started(ws)
        ws.send_json({"type": "finished"})
        ws.send_json({"type": "interrupt", "played_seconds": 1.0, "stop_ms": None})
        assert ask(ws)[0]["type"] == "turn"  # the first thing the server sends back
    assert rig.saved == []


def test_unknown_model_sends_error(rig, monkeypatch):
    async def gone(model_id, transport):
        raise NotFound("model_not_found")

    monkeypatch.setattr(voice, "load_llm", gone)
    with connect(rig) as ws:
        started(ws, model_id=str(uuid.uuid4()))
        ws.send_bytes(TALK)
        assert ws.receive_json() == {
            "type": "error",
            "message": "The model you picked was removed. Ask again to use the default model.",
            "retryable": True,
        }
    assert rig.seen == []


def test_a_new_utterance_cancels_the_running_turn(rig):
    with connect(rig) as ws:
        started(ws)
        ws.send_bytes(SLOW)
        assert until(ws, "transcript")[0]["type"] == "turn"
        second = ask(ws)
        ws.send_json({"type": "finished"})
        ws.receive_json()
    first, newer = rig.seen
    assert rig.cancelled == [first.result.turn_id]
    assert second[0]["id"] == str(newer.result.turn_id)
    [only] = rig.saved  # the cancelled turn saved nothing
    assert only.result is newer.result


def test_interrupt_cancels_and_saves_what_was_heard(rig):
    with connect(rig) as ws:
        started(ws)
        ws.send_bytes(SLOW)
        until(ws, "transcript")
        ws.send_json({"type": "interrupt", "played_seconds": 2.0, "stop_ms": 90})
        message = ws.receive_json()
    [only] = rig.saved
    assert rig.cancelled == [only.result.turn_id]
    assert (only.kind, only.played, only.stop_ms) == ("heard", 2.0, 90)
    assert message == {"type": "saved", "output_id": str(only.result.output_id)}


def test_an_empty_transcript_right_after_an_interrupt_marks_that_interrupt_false(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "interrupt", "played_seconds": 0.4, "stop_ms": 80})
        ws.receive_json()
        ask(ws, MUTE)
        assert ask(ws, MUTE)[-1] == {"type": "done"}  # a second noise does not mark it again
    [interrupted] = rig.saved
    assert rig.false_marks == [interrupted.result.row_id]


def test_a_real_question_after_an_interrupt_leaves_it_unmarked(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "interrupt", "played_seconds": 0.4, "stop_ms": 80})
        ws.receive_json()
        ask(ws)
        ask(ws, MUTE)  # noise later on is not about the interrupt
    assert rig.false_marks == []


def test_a_later_paper_turn_follows_the_last_saved_answer_including_a_cut_off_one(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "finished"})
        whole = ws.receive_json()["output_id"]
        ask(ws)
        ws.send_json({"type": "interrupt", "played_seconds": 1.0, "stop_ms": None})
        cut = ws.receive_json()["output_id"]
        ask(ws)
    assert [turn.parent for turn in rig.seen] == [None, uuid.UUID(whole), uuid.UUID(cut)]


def test_a_turn_that_saved_nothing_leaves_the_parent_unchanged(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "finished"})
        whole = ws.receive_json()["output_id"]
        ask(ws)
        ws.send_json({"type": "interrupt", "played_seconds": 0, "stop_ms": 30})  # nothing was heard
        ask(ws)
    assert [turn.parent for turn in rig.seen] == [None, uuid.UUID(whole), uuid.UUID(whole)]


def test_a_workspace_turn_never_has_a_parent(rig):
    with connect(rig) as ws:
        started(ws, scope="workspace")
        ask(ws)
        ws.send_json({"type": "finished"})
        ws.receive_json()
        ask(ws)
    assert [turn.parent for turn in rig.seen] == [None, None]
    assert rig.seen[0].result.scope.workspace_id == uuid.UUID(START["id"])
    assert [turn.cold for turn in rig.seen] == [True, False]


def test_an_oversized_or_misaligned_utterance_is_ignored_with_an_error_message(rig):
    with connect(rig) as ws:
        started(ws)
        for bad in (b"\0" * (voice.MAX_UTTERANCE_BYTES + 4), b"abc", b""):
            ws.send_bytes(bad)
            message = ws.receive_json()
            assert message["type"] == "error" and message["retryable"] is False
        assert ask(ws)[0]["type"] == "turn"  # the connection is still usable
    assert len(rig.seen) == 1


def test_metrics_land_on_the_current_turn_and_ones_for_an_unknown_turn_are_ignored(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
        ws.send_json({"type": "metrics", "turn": 7, "wait_ms": 1, "output_ms": 2, "total_ms": 3})
        ws.send_json({"type": "metrics", "turn": 1, "wait_ms": 400, "output_ms": 5000, "total_ms": 5400})
        ws.send_json({"type": "finished"})
        ws.receive_json()
    assert rig.saved[0].result.timing == {"wait_ms": 400, "output_ms": 5000, "total_ms": 5400}


def test_a_bad_message_after_start_sends_error_and_keeps_the_connection(rig):
    with connect(rig) as ws:
        started(ws)
        for bad in ("not json", '{"type":"interrupt"}', '{"type":"mystery"}', '{"type":"start"}'):
            ws.send_text(bad)
            assert ws.receive_json()["type"] == "error"
        assert ask(ws)[0]["type"] == "turn"


def test_a_disconnect_cancels_the_running_turn_and_saves_nothing(rig):
    with connect(rig) as ws:
        started(ws)
        ws.send_bytes(SLOW)
        until(ws, "transcript")
    [only] = rig.seen
    assert rig.cancelled == [only.result.turn_id]
    assert rig.saved == []


def test_the_turn_gets_the_speech_provider_the_route_resolved(rig):
    with connect(rig) as ws:
        started(ws)
        ask(ws)
    assert rig.seen[0].speech is rig.speech
