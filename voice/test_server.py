import numpy as np
import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "transcribe", lambda audio: f"heard {len(audio)} samples")
    monkeypatch.setattr(server, "synthesize", lambda text: (np.array([0.0, 0.5], dtype=np.float32), 24000))
    return TestClient(server.app)


def test_health_reports_ready(client):
    assert client.get("/health").json() == {"ready": True, "stt": "whisper-small-int8", "tts": "kokoro-int8"}


def test_transcribe_returns_text(client):
    body = np.zeros(1600, dtype="<f4").tobytes()
    assert client.post("/transcribe", content=body).json() == {"text": "heard 1600 samples"}


def test_transcribe_refuses_over_a_minute_with_413(client):
    assert client.post("/transcribe", content=bytes(server.MAX_UTTERANCE_BYTES + 4)).status_code == 413


def test_transcribe_refuses_a_length_not_divisible_by_4_with_422(client):
    assert client.post("/transcribe", content=bytes(7)).status_code == 422


def test_speak_returns_samples_and_rate(client):
    r = client.post("/speak", json={"text": "Hello."})
    assert r.headers["x-sample-rate"] == "24000"
    assert np.frombuffer(r.content, dtype="<f4").tolist() == [0.0, 0.5]


def test_speak_refuses_empty_text_with_422(client):
    assert client.post("/speak", json={"text": "  "}).status_code == 422


def test_any_request_with_an_origin_header_is_refused_with_403(client):
    assert client.get("/health", headers={"Origin": "http://evil.example"}).status_code == 403
