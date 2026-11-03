"""PaperLab's optional voice program: speech to text and text to speech on the Mac host.

Docker on a Mac has no GPU or Neural Engine, so the API calls this over HTTP (like Ollama).
"""
import hashlib
import time
import urllib.request
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

HERE = Path(__file__).parent
PORT = 8791
MAX_UTTERANCE_BYTES = 16000 * 4 * 60  # one minute of 16 kHz float32
VOICE = "af_heart"
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
# name -> (SHA-256, megabytes)
MODEL_FILES = {
    "kokoro-v1.0.int8.onnx": ("6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb", 88),
    "voices-v1.0.bin": ("bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 27),
}

whisper = None
kokoro = None


def transcribe(audio: np.ndarray) -> str:
    segments, _ = whisper.transcribe(audio, language="en", beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def synthesize(text: str) -> tuple[np.ndarray, int]:
    samples, rate = kokoro.create(text, voice=VOICE, speed=1.0, lang="en-us")
    return np.asarray(samples, dtype=np.float32), rate


app = FastAPI()


@app.middleware("http")
async def refuse_browsers(request: Request, call_next):
    # A web page cannot reach this program: browsers always send Origin on cross-site requests.
    if "origin" in request.headers:
        return JSONResponse({"detail": "Browsers may not call the voice program."}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"ready": True, "stt": "whisper-small-int8", "tts": "kokoro-int8"}


@app.post("/transcribe")
async def transcribe_route(request: Request) -> dict:
    body = await request.body()
    if len(body) > MAX_UTTERANCE_BYTES:
        raise HTTPException(413, "Audio is longer than a minute.")
    if len(body) % 4:
        raise HTTPException(422, "Audio must be 16 kHz float32 samples.")
    return {"text": transcribe(np.frombuffer(body, dtype="<f4"))}


class Speak(BaseModel):
    text: str


@app.post("/speak")
def speak_route(body: Speak) -> Response:
    if not body.text.strip():
        raise HTTPException(422, "Nothing to say.")
    samples, rate = synthesize(body.text)
    return Response(samples.astype("<f4").tobytes(), media_type="application/octet-stream", headers={"X-Sample-Rate": str(rate)})


def ensure_model_files() -> None:
    (HERE / "models").mkdir(exist_ok=True)
    for name, (sha, megabytes) in MODEL_FILES.items():
        path = HERE / "models" / name
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

    ensure_model_files()
    print("Loading models (the first run downloads Whisper small, about 460 MB)...", flush=True)
    whisper = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
    kokoro = Kokoro(str(HERE / "models/kokoro-v1.0.int8.onnx"), str(HERE / "models/voices-v1.0.bin"))
    start = time.perf_counter()
    transcribe(np.zeros(16000, dtype=np.float32))
    synthesize("Ready.")
    print(f"Models warm in {time.perf_counter() - start:.1f}s", flush=True)


if __name__ == "__main__":
    load_models()
    uvicorn.run(app, host="127.0.0.1", port=PORT)
