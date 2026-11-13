"""Asks the running voice program one recorded question, the way the app does, and checks the answer.

Used by .github/workflows/voice.yml on Linux: `python ci_check.py URL WAV WORD...`. Exits 1 with a plain message when
the program never gets ready, the transcript misses a word, or speaking gives no audio.
"""

import json
import sys
import time
import urllib.request
import wave

import numpy as np

READY_WAIT_SECONDS = 15 * 60  # the first start downloads about 600 MB of models
RATE = 16000  # what /transcribe takes: 16 kHz mono float32


def samples_16k(path: str) -> np.ndarray:
    """A 16-bit PCM WAV, any rate and channel count, as 16 kHz mono float32 in [-1, 1]."""
    with wave.open(path) as w:
        if w.getsampwidth() != 2:
            raise SystemExit(f"{path}: only 16-bit WAV files are supported.")
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        audio = audio.reshape(-1, w.getnchannels()).mean(axis=1)
        rate = w.getframerate()
    if rate == RATE:
        return audio
    # ponytail: linear resampling, fine for a speech check; use a polyphase filter if a fixture ever needs better
    times = np.arange(round(len(audio) * RATE / rate)) * rate / RATE
    return np.interp(times, np.arange(len(audio)), audio).astype(np.float32)


def get(url: str, data: bytes | None = None, headers: dict | None = None):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(request, timeout=120) as reply:
        return reply.read(), reply.headers


def wait_until_ready(url: str) -> None:
    deadline = time.monotonic() + READY_WAIT_SECONDS
    last = None
    while time.monotonic() < deadline:
        try:
            health = json.loads(get(f"{url}/health")[0])
        except OSError as e:  # not listening yet
            health = {"stage": f"unreachable ({e})"}
        if health.get("ready"):
            return
        if health.get("stage") == "failed":
            raise SystemExit(f"The voice program failed to get ready: {health.get('detail')}")
        if health.get("stage") != last:
            print(f"voice: {health.get('stage')} {health.get('detail') or ''}", flush=True)
            last = health.get("stage")
        time.sleep(5)
    raise SystemExit(f"The voice program wasn't ready after {READY_WAIT_SECONDS // 60} minutes.")


def main(url: str, wav: str, words: list[str]) -> None:
    wait_until_ready(url)
    body, _ = get(f"{url}/transcribe", samples_16k(wav).astype("<f4").tobytes())
    text = json.loads(body)["text"]
    print(f"heard: {text!r}", flush=True)
    missing = [w for w in words if w.lower() not in text.lower()]
    if missing:
        raise SystemExit(f"The transcript is missing {missing}.")
    audio, headers = get(f"{url}/speak", json.dumps({"text": "Ready."}).encode(), {"Content-Type": "application/json"})
    if len(audio) < 4 or int(headers["X-Sample-Rate"]) <= 0:
        raise SystemExit("Speaking gave no audio.")
    print(f"spoke {len(audio) // 4} samples at {headers['X-Sample-Rate']} Hz", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit("usage: ci_check.py URL WAV WORD...")
    main(sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3:])
