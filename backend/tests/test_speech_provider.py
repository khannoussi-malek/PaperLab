import struct

import httpx
import pytest
from pydantic import ValidationError

from app.api.deps import get_transport
from app.config import Settings
from app.providers.base import SpeechUnavailable
from app.providers.speech import FakeSpeech, SidecarSpeech

pytestmark = pytest.mark.anyio

NOT_RUNNING = "The voice program isn't running. Start it with scripts/voice.sh."


def speech_with(handler) -> SidecarSpeech:
    return SidecarSpeech("http://voice", httpx.MockTransport(handler))


async def test_transcribe_sends_the_raw_samples_and_reads_the_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["origin"], seen["path"] = request.content, request.headers.get("origin"), request.url.path
        return httpx.Response(200, json={"text": "hello there"})

    samples = struct.pack("<3f", 0.1, -0.2, 0.3)
    assert await speech_with(handler).transcribe(samples) == "hello there"
    assert (seen["body"], seen["origin"], seen["path"]) == (samples, None, "/transcribe")


async def test_speak_sends_the_text_and_reads_samples_and_rate():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/speak" and request.content == b'{"text":"Hi."}'
        return httpx.Response(200, content=b"\x00\x01\x02\x03", headers={"X-Sample-Rate": "24000"})

    assert await speech_with(handler).speak("Hi.") == (b"\x00\x01\x02\x03", 24000)


async def test_a_refused_connection_says_how_to_start_the_program():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(SpeechUnavailable) as e:
        await speech_with(handler).transcribe(b"")
    assert str(e.value) == NOT_RUNNING


async def test_a_timeout_counts_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SpeechUnavailable):
        await speech_with(handler).speak("Hi.")


async def test_a_server_error_is_unavailable():
    with pytest.raises(SpeechUnavailable):
        await speech_with(lambda r: httpx.Response(503)).speak("Hi.")


async def test_fake_speech_records_what_it_was_asked_to_say():
    fake = FakeSpeech()
    audio, rate = await fake.speak("One.")
    assert (fake.spoken, rate, len(audio) % 4) == (["One."], 24000, 0)
    assert await fake.transcribe(b"") == "What does this paper say?"


async def test_status_is_ready_when_health_answers(app, client):
    app.dependency_overrides[get_transport] = lambda: httpx.MockTransport(
        lambda r: httpx.Response(200, json={"ready": True, "stt": "x", "tts": "y"})
    )
    assert (await client.get("/api/voice/status")).json() == {"ready": True, "detail": None}


async def test_status_says_how_to_start_the_program_when_it_is_down(app, client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    app.dependency_overrides[get_transport] = lambda: httpx.MockTransport(handler)
    assert (await client.get("/api/voice/status")).json() == {"ready": False, "detail": NOT_RUNNING}


async def test_status_is_not_ready_when_health_says_so(app, client):
    app.dependency_overrides[get_transport] = lambda: httpx.MockTransport(
        lambda r: httpx.Response(200, json={"ready": False})
    )
    body = (await client.get("/api/voice/status")).json()
    assert body["ready"] is False and body["detail"]


@pytest.mark.parametrize("reply", [{"nope": 1}, "not an object"])
async def test_a_malformed_transcribe_reply_is_unavailable(reply):
    with pytest.raises(SpeechUnavailable):
        await speech_with(lambda r: httpx.Response(200, json=reply)).transcribe(b"")
    with pytest.raises(SpeechUnavailable):
        await speech_with(lambda r: httpx.Response(200, content=b"<html>")).transcribe(b"")


@pytest.mark.parametrize("headers", [{}, {"X-Sample-Rate": "fast"}])
async def test_a_malformed_speak_reply_is_unavailable(headers):
    with pytest.raises(SpeechUnavailable):
        await speech_with(lambda r: httpx.Response(200, content=b"\x00", headers=headers)).speak("Hi.")


@pytest.mark.parametrize("content", [b"<html>", b"[1]"])
async def test_a_malformed_health_reply_is_not_ready(content):
    with pytest.raises(SpeechUnavailable):
        await speech_with(lambda r: httpx.Response(200, content=content)).health()


def test_fake_speech_needs_a_test_stack(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DISCOVERY_PROVIDER", raising=False)
    monkeypatch.setenv("SPEECH_PROVIDER", "fake")
    monkeypatch.setenv("PAPERLAB_STACK", "paperlab")
    with pytest.raises(ValidationError, match="scripts/e2e-stack.sh"):
        Settings()


async def test_an_empty_speak_reply_is_no_audio_not_a_failure():
    speech = speech_with(lambda r: httpx.Response(200, content=b"", headers={"X-Sample-Rate": "24000"}))
    assert await speech.speak("Hi.") == (b"", 24000)
