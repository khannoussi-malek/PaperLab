import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import server

HEALTH_FIELDS = {"stt": "whisper-small-int8", "tts": "kokoro-int8"}


@pytest.fixture(autouse=True)
def ready_state(monkeypatch):
    monkeypatch.setattr(server, "STATE", {"stage": "ready", "detail": None}, raising=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "transcribe", lambda audio: f"heard {len(audio)} samples")
    monkeypatch.setattr(server, "synthesize", lambda text: (np.array([0.0, 0.5], dtype=np.float32), 24000))
    return TestClient(server.app)


def test_health_reports_ready(client):
    assert client.get("/health").json() == {"ready": True, "stage": "ready", "detail": None, **HEALTH_FIELDS}


def test_health_says_downloading_before_ready(client, monkeypatch):
    monkeypatch.setattr(server, "STATE", {"stage": "downloading", "detail": None})
    body = client.get("/health").json()
    assert body["ready"] is False and body["stage"] == "downloading"


@pytest.mark.parametrize("route", ["/transcribe", "/speak"])
def test_work_routes_refuse_with_503_until_ready(client, monkeypatch, route):
    monkeypatch.setattr(server, "STATE", {"stage": "loading", "detail": None})
    r = client.post(route, content=bytes(8)) if route == "/transcribe" else client.post(route, json={"text": "Hi."})
    assert r.status_code == 503 and r.json() == {"detail": "Voice is still getting ready."}


def test_a_failed_prepare_keeps_serving_and_says_why(client, monkeypatch):
    def no_disk():
        raise SystemExit("Not enough disk space to download the voice models: 1.0 GB free, 3 GB needed.")

    monkeypatch.setattr(server, "ensure_model_files", no_disk)
    server.prepare()
    body = client.get("/health").json()
    assert body["stage"] == "failed" and body["ready"] is False
    assert "Not enough disk space" in body["detail"]


def test_a_partial_file_is_replaced_on_next_start(monkeypatch, tmp_path):
    good = b"the real model bytes"
    sha = hashlib.sha256(good).hexdigest()
    models = tmp_path / "models"
    models.mkdir()
    (models / "fake.bin").write_bytes(b"trunc")
    monkeypatch.setattr(server, "MODELS_DIR", models)
    monkeypatch.setattr(server, "MODEL_FILES", {"fake.bin": (sha, 1)})
    monkeypatch.setattr(server.shutil, "disk_usage", lambda _: type("U", (), {"free": 10 * 1024**3})())
    monkeypatch.setattr(server.urllib.request, "urlretrieve", lambda url, path: Path(path).write_bytes(good))

    with pytest.raises(SystemExit):
        server.ensure_model_files()
    assert not (models / "fake.bin").exists()

    server.ensure_model_files()
    assert (models / "fake.bin").read_bytes() == good


def test_models_dir_and_host_come_from_the_environment(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "HF_HOME"}
    env.update(VOICE_MODELS_DIR="/x", VOICE_HOST="0.0.0.0")
    code = "import json, os, server; print(json.dumps([str(server.MODELS_DIR), server.HOST, os.environ['HF_HOME']]))"
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=Path(server.__file__).parent,
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == ["/x", "0.0.0.0", "/x/hf"]


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


def test_transcribe_refuses_an_empty_body_with_422(client):
    assert client.post("/transcribe", content=b"").status_code == 422


def test_a_missing_model_with_too_little_disk_refuses_before_downloading(monkeypatch, tmp_path):
    downloads = []
    monkeypatch.setattr(server, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(server.shutil, "disk_usage", lambda _: type("U", (), {"free": 1 * 1024**3})())
    monkeypatch.setattr(server.urllib.request, "urlretrieve", lambda *a: downloads.append(a))
    with pytest.raises(SystemExit) as stop:
        server.ensure_model_files()
    assert "1.0 GB free" in str(stop.value) and "3 GB" in str(stop.value)
    assert downloads == []


def test_health_answers_while_a_transcription_is_running(monkeypatch):
    import threading

    started, release = threading.Event(), threading.Event()

    def slow(audio):
        started.set()
        return "done" if release.wait(5) else "blocked"

    monkeypatch.setattr(server, "transcribe", slow)
    results = {}

    async def run():
        import asyncio

        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            task = asyncio.create_task(c.post("/transcribe", content=bytes(8)))
            await asyncio.to_thread(started.wait, 5)
            results["health"] = await asyncio.wait_for(c.get("/health"), 2)
            release.set()
            results["text"] = (await task).json()

    import asyncio

    asyncio.run(run())
    assert results["health"].status_code == 200 and results["text"] == {"text": "done"}


def test_speak_of_text_kokoro_cant_phonemize_is_empty_audio_not_a_500(client, monkeypatch):
    def nothing(text):
        raise ValueError("Nothing to synthesize ... produced no phonemes")

    monkeypatch.setattr(server, "synthesize", nothing)
    r = client.post("/speak", json={"text": "|---|"})
    assert r.status_code == 200 and r.content == b"" and r.headers["x-sample-rate"] == str(server.SAMPLE_RATE)


def test_any_other_speak_failure_stays_a_500(monkeypatch):
    def broken(text):
        raise ValueError("something else")

    monkeypatch.setattr(server, "synthesize", broken)
    assert TestClient(server.app, raise_server_exceptions=False).post("/speak", json={"text": "Hi."}).status_code == 500
