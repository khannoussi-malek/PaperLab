import wave

import numpy as np

import ci_check


def write_wav(path, samples: np.ndarray, rate: int, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((samples * 32767).astype("<i2").tobytes())


def test_a_16k_mono_file_is_read_as_is(tmp_path):
    write_wav(tmp_path / "a.wav", np.array([0.0, 0.5, -0.5], dtype=np.float32), 16000)
    np.testing.assert_allclose(ci_check.samples_16k(str(tmp_path / "a.wav")), [0.0, 0.5, -0.5], atol=1e-3)


def test_stereo_at_48k_becomes_16k_mono(tmp_path):
    one_second = np.tile(np.array([0.2, 0.4], dtype=np.float32), 48000)  # left 0.2, right 0.4, interleaved
    write_wav(tmp_path / "b.wav", one_second, 48000, channels=2)
    audio = ci_check.samples_16k(str(tmp_path / "b.wav"))
    assert len(audio) == 16000 and audio.dtype == np.float32
    np.testing.assert_allclose(audio, 0.3, atol=1e-3)
