"""PaperLab's optional voice program: speech to text and text to speech.

It runs in its own container (or natively on a Mac developer's machine); the API calls it over HTTP.
"""
import hashlib
import os
import shutil
import threading
import time
import traceback
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

HERE = Path(__file__).parent
PORT = 8791
HOST = os.environ.get("VOICE_HOST", "127.0.0.1")
MODELS_DIR = Path(os.environ.get("VOICE_MODELS_DIR", HERE / "models"))
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))  # before faster_whisper is imported
MAX_UTTERANCE_BYTES = 16000 * 4 * 60  # one minute of 16 kHz float32
VOICE = "af_heart"
SAMPLE_RATE = 24000  # Kokoro's
NO_PHONEMES = "no phonemes"
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
# name -> (SHA-256, megabytes)
MIN_FREE_BYTES = 3 * 1024**3
MODEL_FILES = {
    "kokoro-v1.0.int8.onnx": ("6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb", 88),
    "voices-v1.0.bin": ("bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 27),
}

whisper = None
kokoro = None
STATE = {"stage": "downloading", "detail": None}  # stage: downloading, loading, ready, failed


def transcribe(audio: np.ndarray) -> str:
    segments, _ = whisper.transcribe(audio, language="en", beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def synthesize(text: str) -> tuple[np.ndarray, int]:
    samples, rate = kokoro.create(text, voice=VOICE, speed=1.0, lang="en-us")
    return np.asarray(samples, dtype=np.float32), rate


def set_state(stage: str, detail: str | None = None) -> None:
    global STATE
    STATE = {"stage": stage, "detail": detail}


def require_ready() -> None:
    if STATE["stage"] != "ready":
        raise HTTPException(503, "Voice is still getting ready.")


def prepare() -> None:
    try:
        set_state("downloading")
        ensure_model_files()
        set_state("loading")
        load_models()
        set_state("ready")
    except (Exception, SystemExit) as e:
        traceback.print_exc()
        set_state("failed", str(e))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=prepare, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def refuse_browsers(request: Request, call_next):
    # A web page cannot reach this program: browsers always send Origin on cross-site requests.
    if "origin" in request.headers:
        return JSONResponse({"detail": "Browsers may not call the voice program."}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {
        "ready": STATE["stage"] == "ready",
        "stage": STATE["stage"],
        "detail": STATE["detail"],
        "stt": "whisper-small-int8",
        "tts": "kokoro-int8",
    }


@app.post("/transcribe")
async def transcribe_route(request: Request) -> dict:
    require_ready()
    body = await request.body()
    if len(body) > MAX_UTTERANCE_BYTES:
        raise HTTPException(413, "Audio is longer than a minute.")
    if not body or len(body) % 4:
        raise HTTPException(422, "Audio must be 16 kHz float32 samples.")
    return {"text": await run_in_threadpool(transcribe, np.frombuffer(body, dtype="<f4"))}


class Speak(BaseModel):
    text: str


@app.post("/speak")
async def speak_route(body: Speak) -> Response:
    require_ready()
    if not body.text.strip():
        raise HTTPException(422, "Nothing to say.")
    try:
        samples, rate = await run_in_threadpool(synthesize, body.text)
    except ValueError as e:
        if NO_PHONEMES not in str(e):
            raise
        samples, rate = np.zeros(0, dtype=np.float32), SAMPLE_RATE  # nothing sayable: empty audio, not an error
    return Response(samples.astype("<f4").tobytes(), media_type="application/octet-stream", headers={"X-Sample-Rate": str(rate)})


def ensure_model_files() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    missing = [n for n in MODEL_FILES if not (MODELS_DIR / n).exists()]
    free = shutil.disk_usage(MODELS_DIR).free
    if missing and free < MIN_FREE_BYTES:
        raise SystemExit(f"Not enough disk space to download the voice models: {free / 1024**3:.1f} GB free, 3 GB needed.")
    for name, (sha, megabytes) in MODEL_FILES.items():
        path = MODELS_DIR / name
        if not path.exists():
            print(f"Downloading {name} (about {megabytes} MB)...", flush=True)
            urllib.request.urlretrieve(RELEASE + name, path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            path.unlink()
            raise SystemExit(f"{name} did not match its checksum and was deleted. Run it again.")


def load_models() -> None:
    global whisper, kokoro
    from faster_whisper import WhisperModel
    from kokoro_onnx import Kokoro

    print("Loading models (the first run downloads Whisper small, about 460 MB)...", flush=True)
    whisper = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
    kokoro = Kokoro(str(MODELS_DIR / "kokoro-v1.0.int8.onnx"), str(MODELS_DIR / "voices-v1.0.bin"))
    start = time.perf_counter()
    transcribe(np.zeros(16000, dtype=np.float32))
    synthesize("Ready.")
    print(f"Models warm in {time.perf_counter() - start:.1f}s", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
