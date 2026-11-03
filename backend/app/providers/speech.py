"""The voice program on the host (voice/server.py): speech to text and text to speech. It answers 403 to any request
carrying an Origin header, so none is sent. SPEECH_PROVIDER=fake makes build_speech return FakeSpeech (E2E stack)."""

import asyncio

import httpx

from app.config import settings
from app.providers.base import Speech, SpeechUnavailable

NOT_RUNNING = "The voice program isn't running. Start it with scripts/voice.sh."
BAD_REPLY = "The voice program gave an answer PaperLab could not read. Restart it with scripts/voice.sh."
WORK_TIMEOUT = 60.0
HEALTH_TIMEOUT = 2.0


class SidecarSpeech:
    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.url = url.rstrip("/")
        self.transport = transport

    async def _call(self, method: str, path: str, timeout: float, **kwargs) -> httpx.Response:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as http:
                reply = await http.request(method, self.url + path, **kwargs)
            reply.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise SpeechUnavailable(f"The voice program failed ({e.response.status_code}).") from e
        except httpx.HTTPError as e:  # connection refused, timeout, dropped reply
            raise SpeechUnavailable(NOT_RUNNING) from e
        return reply

    @staticmethod
    def _field(reply: httpx.Response, key: str):
        """One field of the reply's JSON object, or SpeechUnavailable: a 200 from something that isn't the program."""
        try:
            return reply.json()[key]
        except (ValueError, KeyError, TypeError) as e:
            raise SpeechUnavailable(BAD_REPLY) from e

    async def health(self) -> bool:
        reply = await self._call("GET", "/health", HEALTH_TIMEOUT)
        return bool(self._field(reply, "ready"))

    async def transcribe(self, samples: bytes) -> str:
        reply = await self._call("POST", "/transcribe", WORK_TIMEOUT, content=samples)
        text = self._field(reply, "text")
        if not isinstance(text, str):
            raise SpeechUnavailable(BAD_REPLY)
        return text

    async def speak(self, text: str) -> tuple[bytes, int]:
        reply = await self._call("POST", "/speak", WORK_TIMEOUT, json={"text": text})
        try:
            return reply.content, int(reply.headers["X-Sample-Rate"])
        except (KeyError, ValueError) as e:
            raise SpeechUnavailable(BAD_REPLY) from e


class FakeSpeech:
    """Deterministic, offline. `spoken` records what it was asked to say."""

    def __init__(
        self, transcript: str = "What does this paper say?", rate: int = 24000, delay: float = 0.0, samples: int = 240
    ):
        self.transcript = transcript
        self.rate = rate
        self.delay = delay
        self.samples = samples
        self.spoken: list[str] = []

    async def health(self) -> bool:
        return True

    async def transcribe(self, samples: bytes) -> str:
        return self.transcript

    async def speak(self, text: str) -> tuple[bytes, int]:
        self.spoken.append(text)
        if self.delay:
            await asyncio.sleep(self.delay)
        return bytes(4 * self.samples), self.rate  # silence: float32 zeros


FAKE_SPEECH_DELAY = 0.05
FAKE_SPEECH_SECONDS = 8  # long enough that a looping question (voice.spec.ts) restarts while the answer plays


def build_speech(transport: httpx.AsyncBaseTransport | None = None) -> Speech:
    if settings.speech_provider == "fake":
        return FakeSpeech(delay=FAKE_SPEECH_DELAY, samples=24000 * FAKE_SPEECH_SECONDS)
    return SidecarSpeech(settings.speech_url, transport)
